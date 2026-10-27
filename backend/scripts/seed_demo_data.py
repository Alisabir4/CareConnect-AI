import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.main import SessionLocal, User, Specialty, Doctor, Availability, pwd
from datetime import date, timedelta
from sqlalchemy import select

db=SessionLocal()
if not db.scalar(select(User).where(User.email=="admin@careconnect.demo")):
    users=[User(name="Demo Administrator",email="admin@careconnect.demo",password_hash=pwd.hash("DemoPass123!"),role="admin"),User(name="Demo Patient",email="patient@careconnect.demo",password_hash=pwd.hash("DemoPass123!"),role="patient")]
    db.add_all(users)
    specs=[Specialty(name=x) for x in ["Cardiology","Dermatology","Family Medicine","Pediatrics"]]; db.add_all(specs); db.flush()
    names=[("Dr. Maya Chen","Cardiology",12,85,"Preventive cardiology with a focus on accessible, patient-centered care."),("Dr. Omar Rahman","Dermatology",9,70,"General and medical dermatology in a welcoming practice."),("Dr. Sofia Patel","Family Medicine",15,60,"Longitudinal primary care for individuals and families."),("Dr. Lucas Kim","Pediatrics",8,65,"Child and adolescent wellness in a family-friendly setting.")]
    for name,spec,exp,fee,bio in names:
        u=User(name=name,email=name.lower().replace("dr. ","").replace(" ",".")+"@careconnect.demo",password_hash=pwd.hash("DemoPass123!"),role="doctor"); db.add(u); db.flush(); d=Doctor(id=u.id,specialty_id=next(s.id for s in specs if s.name==spec),experience=exp,fee=fee,bio=bio); db.add(d)
        for n in range(1,15):
            day=date.today()+timedelta(days=n)
            if day.weekday()<5:
                for hour in [9,10,11,14,15,16]: db.add(Availability(doctor_id=u.id,day=day,hour=hour))
    db.commit()
    print("Seeded fictional demos. Shared demo password: DemoPass123!")
else: print("Demo data already exists.")
db.close()
