from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
import json
import os
import uuid

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from starlette.concurrency import run_in_threadpool
from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from .report_service import analyze_text, answer_question, extract_pdf_text, normalize_text, ollama_available, processing_mode

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'careconnect.db'}")
SECRET_KEY = os.getenv("JWT_SECRET", "local-development-secret-change-me")
ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("TOKEN_MINUTES", "60"))
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REPORT_BYTES = int(os.getenv("MAX_REPORT_BYTES", str(MAX_UPLOAD_BYTES)))
REPORT_UPLOAD_DIR = ROOT / "report_uploads"
REPORT_UPLOAD_DIR.mkdir(exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

class Base(DeclarativeBase): pass
class Role(str, Enum): patient="patient"; doctor="doctor"; admin="admin"
class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    email: Mapped[str]=mapped_column(String(255), unique=True, index=True)
    name: Mapped[str]=mapped_column(String(160))
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(20), default="patient")
    active: Mapped[bool]=mapped_column(Boolean, default=True)
class Specialty(Base):
    __tablename__="specialties"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100), unique=True)
class Doctor(Base):
    __tablename__="doctors"
    id: Mapped[int]=mapped_column(ForeignKey("users.id"), primary_key=True)
    specialty_id: Mapped[int]=mapped_column(ForeignKey("specialties.id"))
    bio: Mapped[str]=mapped_column(Text, default="")
    experience: Mapped[int]=mapped_column(Integer, default=0)
    fee: Mapped[int]=mapped_column(Integer, default=0)
    specialty: Mapped[Specialty]=relationship()
class Availability(Base):
    __tablename__="availability"
    id: Mapped[int]=mapped_column(primary_key=True)
    doctor_id: Mapped[int]=mapped_column(ForeignKey("doctors.id"), index=True)
    day: Mapped[date]=mapped_column(Date, index=True)
    hour: Mapped[int]=mapped_column(Integer)
    __table_args__=(UniqueConstraint("doctor_id","day","hour"),)
class Appointment(Base):
    __tablename__="appointments"
    id: Mapped[int]=mapped_column(primary_key=True)
    patient_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[int]=mapped_column(ForeignKey("doctors.id"), index=True)
    starts_at: Mapped[datetime]=mapped_column(DateTime, index=True)
    status: Mapped[str]=mapped_column(String(20), default="pending")
    reason: Mapped[str]=mapped_column(String(300), default="")
    note: Mapped[str]=mapped_column(Text, default="")
    __table_args__=(Index("uq_active_doctor_slot","doctor_id","starts_at",unique=True,sqlite_where=text("status NOT IN ('cancelled','rejected')"),postgresql_where=text("status NOT IN ('cancelled','rejected')")),)
class ConsultationNote(Base):
    __tablename__="consultation_notes"
    id: Mapped[int]=mapped_column(primary_key=True)
    appointment_id: Mapped[int]=mapped_column(ForeignKey("appointments.id",ondelete="CASCADE"),unique=True,index=True)
    doctor_id: Mapped[int]=mapped_column(ForeignKey("doctors.id"),index=True)
    patient_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    content: Mapped[str]=mapped_column(Text)
    follow_up: Mapped[date|None]=mapped_column(Date,nullable=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class Notification(Base):
    __tablename__="notifications"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    appointment_id: Mapped[int|None]=mapped_column(ForeignKey("appointments.id",ondelete="SET NULL"),nullable=True)
    title: Mapped[str]=mapped_column(String(120))
    message: Mapped[str]=mapped_column(String(300))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)
    read_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
class Document(Base):
    __tablename__="documents"
    id: Mapped[int]=mapped_column(primary_key=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str]=mapped_column(String(255))
    path: Mapped[str]=mapped_column(String(500))
    extracted_text: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
class MedicalReport(Base):
    __tablename__="medical_reports"
    id: Mapped[int]=mapped_column(primary_key=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    filename: Mapped[str]=mapped_column(String(255))
    storage_key: Mapped[str]=mapped_column(String(80),unique=True)
    extracted_text: Mapped[str]=mapped_column(Text,default="")
    analysis_json: Mapped[str]=mapped_column(Text,default="{}")
    status: Mapped[str]=mapped_column(String(20),default="processed")
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)
class ReportMessage(Base):
    __tablename__="report_messages"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("medical_reports.id",ondelete="CASCADE"),index=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    role: Mapped[str]=mapped_column(String(10))
    content: Mapped[str]=mapped_column(Text)
    evidence_json: Mapped[str]=mapped_column(Text,default="[]")
    processing_mode: Mapped[str]=mapped_column(String(40),default="Local rules and retrieval")
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)

Base.metadata.create_all(engine)
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def user_out(u): return {"id":u.id,"name":u.name,"email":u.email,"role":u.role}
def current_user(token: str=Depends(oauth), db: Session=Depends(get_db)):
    try: uid=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"]
    except (JWTError, KeyError): raise HTTPException(401,"Invalid or expired session")
    u=db.get(User,int(uid))
    if not u or not u.active: raise HTTPException(401,"Account unavailable")
    return u
def roles(*allowed):
    def check(u=Depends(current_user)):
        if u.role not in allowed: raise HTTPException(403,"Insufficient permissions")
        return u
    return check
class Register(BaseModel):
    name:str
    email:str
    password:str
    @field_validator("email")
    @classmethod
    def valid_email(cls,value):
        if len(value)>255 or value.count("@")!=1 or "." not in value.rsplit("@",1)[-1]: raise ValueError("Enter a valid email address")
        return value.lower()
class Login(BaseModel):
    email:str
    password:str
    @field_validator("email")
    @classmethod
    def normalized_email(cls,value): return value.lower()
class Book(BaseModel): doctor_id:int; starts_at:datetime; reason:str=""
class StatusUpdate(BaseModel): status:str
class AvailabilityIn(BaseModel): day:date; hours:list[int]
class NoShowInput(BaseModel):
    lead_days:int=Field(ge=0,le=365)
    weekday:int=Field(ge=0,le=6)
    hour:int=Field(ge=0,le=23)
class NoteInput(BaseModel):
    content:str=Field(min_length=1,max_length=10000)
    follow_up:date|None=None
class ReportQuestion(BaseModel):
    question:str=Field(min_length=2,max_length=1000)
class ReportOut(BaseModel):
    id:int
    filename:str
    created_at:datetime
    status:str
class ReportUploadOut(ReportOut):
    processing_mode:str
    message:str
class ReportAnalysisOut(BaseModel):
    overview:dict
    results:list[dict]
    outside_range:list[dict]
    term_explanations:list[dict]
    questions_for_clinician:list[str]
    missing_or_unclear:list[str]
    sources:list[dict]
    processing_mode:str
    disclaimer:str
class ReportDetailOut(ReportOut):
    analysis:ReportAnalysisOut
    processing_mode:str
class ReportAnswerOut(BaseModel):
    answer:str
    evidence:list[str]
    processing_mode:str
class ReportMessageOut(BaseModel):
    id:int
    role:str
    content:str
    evidence:list[str]
    processing_mode:str
    created_at:datetime
class UserStatusInput(BaseModel): active:bool
class AdminDoctorInput(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    email:str
    password:str=Field(min_length=8,max_length=72)
    specialty_id:int
    bio:str=Field(default="",max_length=3000)
    experience:int=Field(default=0,ge=0,le=80)
    fee:int=Field(default=0,ge=0,le=100000)

def notify(db:Session,user_id:int,title:str,message:str,appointment_id:int|None=None):
    db.add(Notification(user_id=user_id,title=title,message=message,appointment_id=appointment_id))

app=FastAPI(title="CareConnect AI", version="1.0.0", description="Portfolio demonstration with fictional records; not medical advice.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("FRONTEND_ORIGINS","http://localhost:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
@app.get("/api/v1/health")
def health(): return {"status":"ok","demo_data":"fictional"}
@app.post("/api/v1/auth/register", status_code=201)
def register(body:Register, db:Session=Depends(get_db)):
    if len(body.password)<8: raise HTTPException(422,"Password must be at least 8 characters")
    if len(body.password.encode("utf-8"))>72: raise HTTPException(422,"Password must be 72 UTF-8 bytes or fewer")
    if db.scalar(select(User).where(User.email==body.email)): raise HTTPException(409,"Email already registered")
    u=User(email=body.email,name=body.name,password_hash=pwd.hash(body.password),role="patient"); db.add(u); db.commit(); db.refresh(u); return user_out(u)
@app.post("/api/v1/auth/login")
def login(body:Login, db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==body.email))
    if not u or not u.active or not pwd.verify(body.password,u.password_hash): raise HTTPException(401,"Email or password is incorrect")
    token=jwt.encode({"sub":str(u.id),"exp":datetime.now(timezone.utc)+timedelta(minutes=TOKEN_MINUTES)},SECRET_KEY,algorithm=ALGORITHM)
    return {"access_token":token,"token_type":"bearer","user":user_out(u)}
@app.get("/api/v1/auth/me")
def me(u=Depends(current_user)): return user_out(u)
@app.get("/api/v1/doctors")
def doctors(search:str="", specialty:str="", sort:str="name", db:Session=Depends(get_db)):
    q=select(Doctor,User,Specialty).join(User,User.id==Doctor.id).join(Specialty)
    if search: q=q.where(User.name.ilike(f"%{search}%"))
    if specialty: q=q.where(Specialty.name==specialty)
    rows=db.execute(q).all(); out=[{"id":d.id,"name":u.name,"specialty":s.name,"bio":d.bio,"experience":d.experience,"fee":d.fee,"email":u.email} for d,u,s in rows]
    return sorted(out,key=lambda x:x["fee"] if sort=="fee" else x["name"])
@app.get("/api/v1/specialties")
def specialties(db:Session=Depends(get_db)): return [{"id":s.id,"name":s.name} for s in db.scalars(select(Specialty).order_by(Specialty.name))]
@app.get("/api/v1/doctors/{doctor_id}")
def doctor_detail(doctor_id:int,db:Session=Depends(get_db)):
    d=db.get(Doctor,doctor_id)
    if not d: raise HTTPException(404,"Doctor not found")
    u=db.get(User,d.id); return {"id":d.id,"name":u.name,"specialty":d.specialty.name,"bio":d.bio,"experience":d.experience,"fee":d.fee}
@app.get("/api/v1/doctors/{doctor_id}/availability")
def doctor_availability(doctor_id:int,db:Session=Depends(get_db)):
    return [{"day":a.day.isoformat(),"hour":a.hour} for a in db.scalars(select(Availability).where(Availability.doctor_id==doctor_id,Availability.day>=date.today()).order_by(Availability.day,Availability.hour))]
@app.post("/api/v1/appointments",status_code=201)
def book(body:Book,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    if body.starts_at.tzinfo: starts=body.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
    else: starts=body.starts_at
    if starts<=datetime.utcnow(): raise HTTPException(422,"Appointment must be in the future")
    if not db.get(Doctor,body.doctor_id): raise HTTPException(404,"Doctor not found")
    if not db.scalar(select(Availability).where(Availability.doctor_id==body.doctor_id,Availability.day==starts.date(),Availability.hour==starts.hour)): raise HTTPException(409,"This time is not available")
    if starts.minute!=0 or starts.second!=0 or starts.microsecond!=0: raise HTTPException(422,"Appointments must start on the published hour")
    if db.scalar(select(Appointment).where(Appointment.doctor_id==body.doctor_id,Appointment.starts_at==starts,Appointment.status.not_in(["cancelled","rejected"]))): raise HTTPException(409,"This appointment slot is already booked")
    a=Appointment(patient_id=u.id,doctor_id=body.doctor_id,starts_at=starts,reason=body.reason); db.add(a)
    try: db.commit()
    except Exception: db.rollback(); raise HTTPException(409,"This appointment slot is already booked")
    notify(db,body.doctor_id,"New appointment request","A patient requested an appointment. Review your schedule.",a.id)
    notify(db,u.id,"Request received","Your appointment request has been sent to the care team.",a.id)
    db.commit(); db.refresh(a); return appointment_out(a,db)
def appointment_out(a,db): return {"id":a.id,"doctor_id":a.doctor_id,"doctor_name":db.get(User,a.doctor_id).name,"patient_id":a.patient_id,"patient_name":db.get(User,a.patient_id).name,"starts_at":a.starts_at.isoformat()+"Z","status":a.status,"reason":a.reason}
@app.get("/api/v1/appointments")
def appointments(u=Depends(current_user),db:Session=Depends(get_db)):
    q=select(Appointment)
    if u.role=="patient": q=q.where(Appointment.patient_id==u.id)
    elif u.role=="doctor": q=q.where(Appointment.doctor_id==u.id)
    return [appointment_out(a,db) for a in db.scalars(q.order_by(Appointment.starts_at))]
@app.patch("/api/v1/appointments/{aid}/status")
def update_status(aid:int,body:StatusUpdate,u=Depends(current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,aid)
    if not a: raise HTTPException(404,"Appointment not found")
    if u.role=="patient" and a.patient_id!=u.id: raise HTTPException(403,"Not your appointment")
    if u.role=="doctor" and a.doctor_id!=u.id: raise HTTPException(403,"Not your appointment")
    transitions={"patient":{"cancelled"},"doctor":{"confirmed","rejected","completed","no-show","cancelled"},"admin":{"confirmed","rejected","completed","no-show","cancelled"}}
    if body.status not in transitions.get(u.role,set()): raise HTTPException(403,"This role cannot set that appointment status")
    if body.status not in {"pending","confirmed","rejected","cancelled","completed","no-show"}: raise HTTPException(422,"Invalid appointment status")
    a.status=body.status
    notify(db,a.patient_id,"Appointment updated",f"Your appointment status is now {body.status}.",a.id)
    db.commit(); return appointment_out(a,db)
@app.patch("/api/v1/appointments/{aid}/reschedule")
def reschedule(aid:int,body:Book,u=Depends(current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,aid)
    if not a or (u.role=="patient" and a.patient_id!=u.id) or (u.role=="doctor" and a.doctor_id!=u.id): raise HTTPException(404,"Appointment not found")
    if u.role not in {"patient","doctor","admin"}: raise HTTPException(403,"Not authorized")
    if a.status not in {"pending","confirmed"}: raise HTTPException(409,"Only pending or confirmed appointments can be rescheduled")
    if body.doctor_id!=a.doctor_id: raise HTTPException(422,"Rescheduling must keep the assigned doctor")
    starts=body.starts_at.astimezone(timezone.utc).replace(tzinfo=None) if body.starts_at.tzinfo else body.starts_at
    if starts<=datetime.utcnow(): raise HTTPException(422,"Appointment must be in the future")
    if starts.minute!=0 or starts.second!=0 or starts.microsecond!=0: raise HTTPException(422,"Appointments must start on the published hour")
    if not db.scalar(select(Availability).where(Availability.doctor_id==a.doctor_id,Availability.day==starts.date(),Availability.hour==starts.hour)): raise HTTPException(409,"This time is not available")
    conflict=db.scalar(select(Appointment).where(Appointment.doctor_id==a.doctor_id,Appointment.starts_at==starts,Appointment.id!=aid,Appointment.status.not_in(["cancelled","rejected"])))
    if conflict: raise HTTPException(409,"This appointment slot is already booked")
    a.starts_at=starts; a.status="pending"; a.reason=body.reason or a.reason
    try: db.commit()
    except Exception: db.rollback(); raise HTTPException(409,"This appointment slot is already booked")
    notify(db,a.patient_id,"Appointment rescheduled","Your appointment time changed and is awaiting confirmation.",a.id)
    notify(db,a.doctor_id,"Appointment rescheduled","An appointment request has a new proposed time.",a.id)
    db.commit(); return appointment_out(a,db)
@app.get("/api/v1/patients/me")
def patient_me(u=Depends(roles("patient"))): return user_out(u)
@app.get("/api/v1/patients/me/appointments")
def my_appointments(u=Depends(roles("patient")),db:Session=Depends(get_db)): return appointments(u,db)
@app.post("/api/v1/documents",status_code=201)
async def upload_document(file:UploadFile=File(...),u=Depends(roles("patient")),db:Session=Depends(get_db)):
    if file.content_type!="application/pdf" or not file.filename.lower().endswith(".pdf"): raise HTTPException(415,"Upload a PDF document")
    data=await file.read(MAX_UPLOAD_BYTES+1)
    if len(data)>MAX_UPLOAD_BYTES: raise HTTPException(413,"PDF must be 10 MB or smaller")
    if not data.startswith(b"%PDF-"): raise HTTPException(415,"File content is not a valid PDF")
    import fitz
    safe=f"{u.id}_{uuid.uuid4().hex}.pdf"; path=UPLOAD_DIR/safe; path.write_bytes(data)
    try:
        with fitz.open(stream=data,filetype="pdf") as doc: extracted="\n".join(p.get_text() for p in doc).strip()
    except Exception:
        path.unlink(missing_ok=True); raise HTTPException(415,"The uploaded PDF could not be read")
    d=Document(owner_id=u.id,filename=Path(file.filename).name,path=safe,extracted_text=extracted); db.add(d); db.commit(); db.refresh(d)
    return {"id":d.id,"filename":d.filename,"status":"processed" if extracted else "no_text","message":"Text extracted" if extracted else "No selectable text found; this scanned PDF requires OCR."}
@app.get("/api/v1/documents")
def list_documents(u=Depends(current_user),db:Session=Depends(get_db)):
    q=select(Document)
    if u.role=="patient": q=q.where(Document.owner_id==u.id)
    elif u.role=="doctor": raise HTTPException(403,"Document access requires an authorized consultation")
    return [{"id":d.id,"filename":d.filename,"created_at":d.created_at.isoformat()} for d in db.scalars(q)]
@app.post("/api/v1/documents/{did}/analyze")
def analyze_document(did:int,u=Depends(current_user),db:Session=Depends(get_db)):
    d=db.get(Document,did)
    if not d or (u.role=="patient" and d.owner_id!=u.id): raise HTTPException(404,"Document not found")
    if u.role=="doctor": raise HTTPException(403,"Not authorized")
    import re
    terms=sorted({x.lower() for x in re.findall(r"\b[A-Za-z]{5,}\b",d.extracted_text)})[:12]
    dates=re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b",d.extracted_text)
    return {"filename":d.filename,"summary":"Keyword-based overview of extracted text. Review the source document; this is not a diagnosis or treatment recommendation.","key_terms":terms,"dates":dates,"characters":len(d.extracted_text),"text_available":bool(d.extracted_text)}
@app.delete("/api/v1/documents/{did}")
def delete_document(did:int,u=Depends(current_user),db:Session=Depends(get_db)):
    d=db.get(Document,did)
    if not d or (u.role=="patient" and d.owner_id!=u.id): raise HTTPException(404,"Document not found")
    if u.role=="doctor": raise HTTPException(403,"Not authorized")
    (UPLOAD_DIR/d.path).unlink(missing_ok=True); db.delete(d); db.commit(); return {"deleted":True}

def report_out(report:MedicalReport):
    return {"id":report.id,"filename":report.filename,"created_at":report.created_at.isoformat(),"status":report.status}

def owned_report(report_id:int,u:User,db:Session):
    report=db.scalar(select(MedicalReport).where(MedicalReport.id==report_id,MedicalReport.owner_id==u.id))
    if not report: raise HTTPException(404,"Report not found")
    return report

@app.post("/api/v1/reports/upload",status_code=201,response_model=ReportUploadOut)
async def upload_report(file:UploadFile=File(...),u=Depends(roles("patient")),db:Session=Depends(get_db)):
    filename=Path(file.filename or "").name
    if not filename.lower().endswith(".pdf") or file.content_type!="application/pdf":
        raise HTTPException(415,"Upload a PDF laboratory report")
    data=await file.read(MAX_REPORT_BYTES+1)
    if len(data)>MAX_REPORT_BYTES: raise HTTPException(413,f"PDF must be {MAX_REPORT_BYTES // (1024*1024)} MB or smaller")
    if not data.startswith(b"%PDF-"): raise HTTPException(415,"File content is not a valid PDF")
    storage_key=uuid.uuid4().hex+".pdf"; path=REPORT_UPLOAD_DIR/storage_key
    try:
        extracted=await run_in_threadpool(extract_pdf_text,data)
    except ValueError as exc:
        if str(exc)=="encrypted": raise HTTPException(415,"Encrypted PDFs are not supported")
        if str(exc)=="empty": raise HTTPException(422,"The PDF contains no readable pages")
        if str(exc)=="too_many_pages": raise HTTPException(413,"PDF exceeds the 250 page processing limit")
        raise HTTPException(415,"The uploaded PDF could not be read")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(415,"The uploaded PDF could not be read")
    if not extracted: raise HTTPException(422,"No selectable text was found. Scanned PDFs need OCR, which is not available in this demo.")
    # Never return the storage path/key or log extracted health text.
    path.write_bytes(data)
    report=MedicalReport(owner_id=u.id,filename=filename[:255],storage_key=storage_key,
                         extracted_text=extracted,analysis_json=json.dumps(analyze_text(extracted)),status="processed")
    try:
        db.add(report); db.commit(); db.refresh(report)
    except Exception:
        db.rollback(); path.unlink(missing_ok=True); raise HTTPException(500,"Report could not be saved")
    return {**report_out(report),"processing_mode":processing_mode(),"message":"Report text extracted locally"}

@app.get("/api/v1/reports",response_model=list[ReportOut])
def list_reports(u=Depends(roles("patient")),db:Session=Depends(get_db)):
    return [report_out(r) for r in db.scalars(select(MedicalReport).where(MedicalReport.owner_id==u.id).order_by(MedicalReport.created_at.desc()).limit(100))]

@app.get("/api/v1/reports/provider")
def report_provider(u=Depends(roles("patient"))):
    available=ollama_available()
    return {"processing_mode":"Optional local language model" if available else "Local rules and retrieval",
            "optional_local_model_available":available,
            "limitation":"Without an available configured local model, answers use keyword retrieval and do not provide generated clinical interpretation."}

@app.get("/api/v1/reports/{report_id}",response_model=ReportDetailOut)
def get_report(report_id:int,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db)
    return {**report_out(report),"analysis":json.loads(report.analysis_json),"processing_mode":processing_mode()}

@app.get("/api/v1/reports/{report_id}/analysis",response_model=ReportAnalysisOut)
def get_report_analysis(report_id:int,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db)
    return json.loads(report.analysis_json)

@app.post("/api/v1/reports/{report_id}/analyze",response_model=ReportAnalysisOut)
def analyze_report(report_id:int,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db)
    # Deterministic and idempotent: repeated requests replace the same analysis.
    report.analysis_json=json.dumps(analyze_text(report.extracted_text)); db.commit()
    return json.loads(report.analysis_json)

@app.post("/api/v1/reports/{report_id}/chat",response_model=ReportAnswerOut)
def ask_report(report_id:int,body:ReportQuestion,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db)
    history=[{"role":m.role,"content":m.content} for m in db.scalars(select(ReportMessage).where(ReportMessage.report_id==report.id,ReportMessage.owner_id==u.id).order_by(ReportMessage.created_at.desc()).limit(10))]
    result=answer_question(report.extracted_text,body.question,list(reversed(history)))
    db.add_all([ReportMessage(report_id=report.id,owner_id=u.id,role="user",content=body.question),
                ReportMessage(report_id=report.id,owner_id=u.id,role="assistant",content=result["answer"],evidence_json=json.dumps(result["evidence"]),processing_mode=result["processing_mode"])])
    db.commit()
    return result

@app.get("/api/v1/reports/{report_id}/chat",response_model=list[ReportMessageOut])
def report_chat_history(report_id:int,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db)
    rows=db.scalars(select(ReportMessage).where(ReportMessage.report_id==report.id,ReportMessage.owner_id==u.id).order_by(ReportMessage.created_at).limit(100))
    return [{"id":m.id,"role":m.role,"content":m.content,"evidence":json.loads(m.evidence_json),"processing_mode":m.processing_mode,"created_at":m.created_at.isoformat()} for m in rows]

@app.delete("/api/v1/reports/{report_id}/chat")
def clear_report_chat(report_id:int,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db)
    db.query(ReportMessage).filter_by(report_id=report.id,owner_id=u.id).delete(synchronize_session=False); db.commit()
    return {"cleared":True}

@app.delete("/api/v1/reports/{report_id}")
def delete_report(report_id:int,u=Depends(roles("patient")),db:Session=Depends(get_db)):
    report=owned_report(report_id,u,db); storage_key=report.storage_key
    db.query(ReportMessage).filter_by(report_id=report.id,owner_id=u.id).delete(synchronize_session=False)
    db.delete(report); db.commit()
    # Storage identifiers are generated by the server and constrained to basenames.
    (REPORT_UPLOAD_DIR/Path(storage_key).name).unlink(missing_ok=True)
    return {"deleted":True}

@app.put("/api/v1/appointments/{aid}/notes")
def save_consultation_note(aid:int,body:NoteInput,u=Depends(roles("doctor")),db:Session=Depends(get_db)):
    a=db.get(Appointment,aid)
    if not a or a.doctor_id!=u.id: raise HTTPException(404,"Appointment not found")
    if a.status not in {"confirmed","completed","no-show"}: raise HTTPException(409,"Notes require a confirmed or completed consultation")
    note=db.scalar(select(ConsultationNote).where(ConsultationNote.appointment_id==aid))
    if note is None:
        note=ConsultationNote(appointment_id=aid,doctor_id=u.id,patient_id=a.patient_id,content=body.content,follow_up=body.follow_up); db.add(note)
    else:
        note.content=body.content; note.follow_up=body.follow_up; note.updated_at=datetime.utcnow()
    notify(db,a.patient_id,"Visit note updated","Your clinician added a consultation note.",a.id)
    db.commit(); db.refresh(note)
    return {"id":note.id,"appointment_id":aid,"content":note.content,"follow_up":note.follow_up,"updated_at":note.updated_at.isoformat()}
@app.get("/api/v1/appointments/{aid}/notes")
def get_consultation_note(aid:int,u=Depends(current_user),db:Session=Depends(get_db)):
    a=db.get(Appointment,aid)
    if not a or not ((u.role=="patient" and a.patient_id==u.id) or (u.role=="doctor" and a.doctor_id==u.id)): raise HTTPException(404,"Appointment not found")
    note=db.scalar(select(ConsultationNote).where(ConsultationNote.appointment_id==aid))
    if not note: raise HTTPException(404,"No consultation note is available")
    return {"id":note.id,"appointment_id":aid,"content":note.content,"follow_up":note.follow_up,"updated_at":note.updated_at.isoformat()}
@app.get("/api/v1/notifications")
def get_notifications(u=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Notification).where(Notification.user_id==u.id).order_by(Notification.created_at.desc()).limit(50))
    return [{"id":n.id,"title":n.title,"message":n.message,"appointment_id":n.appointment_id,"created_at":n.created_at.isoformat(),"read":n.read_at is not None} for n in rows]
@app.patch("/api/v1/notifications/{nid}/read")
def read_notification(nid:int,u=Depends(current_user),db:Session=Depends(get_db)):
    n=db.get(Notification,nid)
    if not n or n.user_id!=u.id: raise HTTPException(404,"Notification not found")
    if n.read_at is None: n.read_at=datetime.utcnow(); db.commit()
    return {"id":nid,"read":True}
@app.post("/api/v1/ml/no-show/predict")
def predict(body:NoShowInput,u=Depends(roles("admin","doctor"))):
    try:
        import joblib
        import json
        import sklearn
        metadata=json.loads((ROOT/"models"/"metrics.json").read_text())
        if metadata.get("sklearn_version")!=sklearn.__version__:
            raise HTTPException(503,"No-show model version mismatch. Retrain it with the active backend environment.")
        model=joblib.load(ROOT/"models"/"no_show.joblib")
    except HTTPException: raise
    except Exception: raise HTTPException(503,"No-show model unavailable. Train it with backend/scripts/train_no_show_model.py.")
    try: score=float(model.predict_proba([[body.lead_days,body.weekday,body.hour]])[0][1])
    except Exception: raise HTTPException(503,"No-show model artifact is incompatible. Retrain it with the active backend environment.")
    return {"risk":score,"category":"low" if score<.25 else "moderate" if score<.55 else "high","thresholds":{"low":"<0.25","moderate":"0.25–0.54","high":">=0.55"},"disclaimer":"Predictions are uncertain and must not be used to deny care or penalize patients."}
@app.get("/api/v1/ml/metrics")
def ml_metrics(u=Depends(roles("admin","doctor"))):
    p=ROOT/"models"/"metrics.json"
    if not p.exists(): return {"available":False,"message":"No evaluation report. Train and evaluate the model first."}
    report=__import__("json").loads(p.read_text())
    baseline=report.get("baseline",{})
    report["metrics"]={**report.get("metrics",{}),**{f"baseline_{key}":value for key,value in baseline.items() if isinstance(value,(int,float))}}
    return report
@app.get("/api/v1/admin/overview")
def admin_overview(u=Depends(roles("admin")),db:Session=Depends(get_db)):
    return {"users":db.query(User).count(),"doctors":db.query(Doctor).count(),"appointments":db.query(Appointment).count(),"documents":db.query(Document).count(),"fictional_demo_data":True}
@app.get("/api/v1/admin/users")
def admin_users(u=Depends(roles("admin")),db:Session=Depends(get_db)): return [{**user_out(x),"active":x.active} for x in db.scalars(select(User))]
@app.get("/api/v1/admin/appointments")
def admin_appointments(u=Depends(roles("admin")),db:Session=Depends(get_db)): return [appointment_out(a,db) for a in db.scalars(select(Appointment))]
@app.patch("/api/v1/admin/users/{uid}/status")
def admin_user_status(uid:int,body:UserStatusInput,u=Depends(roles("admin")),db:Session=Depends(get_db)):
    target=db.get(User,uid)
    if not target: raise HTTPException(404,"User not found")
    target.active=body.active; db.commit(); return {"id":uid,"active":target.active}
@app.post("/api/v1/admin/doctors",status_code=201)
def admin_create_doctor(body:AdminDoctorInput,u=Depends(roles("admin")),db:Session=Depends(get_db)):
    if not db.get(Specialty,body.specialty_id): raise HTTPException(404,"Specialty not found")
    if len(body.password.encode("utf-8"))>72: raise HTTPException(422,"Password must be 72 UTF-8 bytes or fewer")
    email=body.email.strip().lower()
    if email.count("@")!=1 or "." not in email.rsplit("@",1)[-1]: raise HTTPException(422,"Enter a valid email address")
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email already registered")
    target=User(name=body.name.strip(),email=email,password_hash=pwd.hash(body.password),role="doctor"); db.add(target); db.flush()
    d=Doctor(id=target.id,specialty_id=body.specialty_id,bio=body.bio,experience=body.experience,fee=body.fee); db.add(d); db.commit()
    return {"id":d.id,"name":target.name,"specialty":d.specialty.name,"experience":d.experience,"fee":d.fee}
@app.get("/api/v1/doctor/me/appointments")
def doctor_appointments(u=Depends(roles("doctor")),db:Session=Depends(get_db)): return appointments(u,db)
@app.post("/api/v1/doctor/me/availability")
def set_availability(body:AvailabilityIn,u=Depends(roles("doctor")),db:Session=Depends(get_db)):
    if body.day<date.today() or any(h<0 or h>23 for h in body.hours): raise HTTPException(422,"Invalid day or hours")
    db.query(Availability).filter_by(doctor_id=u.id,day=body.day).delete()
    db.add_all([Availability(doctor_id=u.id,day=body.day,hour=h) for h in sorted(set(body.hours))]); db.commit(); return {"day":body.day,"hours":sorted(set(body.hours))}
