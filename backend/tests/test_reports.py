import uuid
from datetime import datetime

import fitz
from fastapi.testclient import TestClient

from app import main
from app.main import MedicalReport, ReportMessage, SessionLocal, User, app, pwd
from app.report_service import analyze_text, answer_question, normalize_text, retrieve

client = TestClient(app)


def patient_headers():
    email=f"report-{uuid.uuid4().hex}@example.test"
    created=client.post("/api/v1/auth/register",json={"name":"Fictional Report Patient","email":email,"password":"a-long-demo-password"})
    assert created.status_code==201
    token=client.post("/api/v1/auth/login",json={"email":email,"password":"a-long-demo-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def pdf_bytes(text="Fictional laboratory report\nHemoglobin 13.2 g/dL 12.0-16.0\nGlucose 118 mg/dL 70-99 H"):
    doc=fitz.open(); page=doc.new_page(); page.insert_text((50,60),text); payload=doc.tobytes(); doc.close(); return payload


def upload(headers,payload=None,filename="fictional.pdf",mime="application/pdf"):
    return client.post("/api/v1/reports/upload",headers=headers,files={"file":(filename,payload if payload is not None else pdf_bytes(),mime)})


def test_report_pdf_upload_analysis_and_evidence_chat_cleanup():
    headers=patient_headers()
    created=upload(headers)
    assert created.status_code==201,created.text
    report_id=created.json()["id"]
    details=client.get(f"/api/v1/reports/{report_id}",headers=headers).json()
    assert details["analysis"]["results"][0]["value"]=="13.2"
    assert details["analysis"]["results"][0]["unit"]=="g/dL"
    assert details["analysis"]["results"][0]["reference_range"]=="12.0–16.0"
    assert details["analysis"]["results"][0]["status"]=="within"
    assert details["analysis"]["outside_range"][0]["name"]=="Glucose"
    assert "not a diagnosis" in details["analysis"]["disclaimer"].lower()
    asked=client.post(f"/api/v1/reports/{report_id}/chat",headers=headers,json={"question":"What is the glucose value?"})
    assert asked.status_code==200 and "Glucose 118 mg/dL" in asked.json()["evidence"][0]
    history=client.get(f"/api/v1/reports/{report_id}/chat",headers=headers).json()
    assert len(history)==2 and history[1]["role"]=="assistant"
    assert client.delete(f"/api/v1/reports/{report_id}/chat",headers=headers).json()=={"cleared":True}
    assert client.get(f"/api/v1/reports/{report_id}/chat",headers=headers).json()==[]
    db=SessionLocal()
    try: storage_key=db.get(MedicalReport,report_id).storage_key
    finally: db.close()
    assert client.delete(f"/api/v1/reports/{report_id}",headers=headers).status_code==200
    assert not (main.REPORT_UPLOAD_DIR/storage_key).exists()
    db=SessionLocal()
    try:
        assert db.get(MedicalReport,report_id) is None
        assert db.query(ReportMessage).filter_by(report_id=report_id).count()==0
    finally: db.close()


def test_report_rejects_bad_mime_content_malformed_and_empty_pdf():
    headers=patient_headers()
    assert upload(headers,pdf_bytes(),filename="report.pdf",mime="application/octet-stream").status_code==415
    assert upload(headers,b"not a pdf").status_code==415
    assert upload(headers,b"%PDF-this is malformed").status_code==415
    empty=fitz.open(); empty.new_page(); payload=empty.tobytes(); empty.close()
    assert upload(headers,payload).status_code==422


def test_report_size_limit_and_content_preservation(monkeypatch):
    headers=patient_headers()
    monkeypatch.setattr(main,"MAX_REPORT_BYTES",64)
    assert upload(headers,pdf_bytes()).status_code==413
    normalized=normalize_text("Sodium −1.25 mmol/L <= 4.20")
    assert "-1.25 mmol/L" in normalized and "<= 4.20" in normalized


def test_parser_marks_missing_or_ambiguous_range_unknown_and_does_not_invent():
    analysis=analyze_text("Fictional laboratory report\nFerritin 42 ng/mL\nSodium 139 mmol/L 135-145")
    ferritin=next(r for r in analysis["results"] if r["name"]=="Ferritin")
    assert ferritin["status"]=="unknown" and ferritin["reference_range"] is None
    assert next(r for r in analysis["results"] if r["name"]=="Sodium")["status"]=="within"
    assert all(r["name"] not in {"Hemoglobin","Glucose"} for r in analysis["results"])
    non_lab=analyze_text("Fictional appointment letter. Visit date 2026-04-02.")
    assert non_lab["overview"]["report_type"]=="Unidentified / non-laboratory document"


def test_report_ownership_blocks_cross_patient_and_admin_access():
    owner=patient_headers(); other=patient_headers()
    report=upload(owner).json(); rid=report["id"]
    for method,path,kwargs in [
        ("get",f"/api/v1/reports/{rid}",{}),
        ("get",f"/api/v1/reports/{rid}/analysis",{}),
        ("get",f"/api/v1/reports/{rid}/chat",{}),
        ("post",f"/api/v1/reports/{rid}/analyze",{}),
        ("post",f"/api/v1/reports/{rid}/chat",{"json":{"question":"glucose?"}}),
        ("delete",f"/api/v1/reports/{rid}",{}),
    ]:
        response=getattr(client,method)(path,headers=other,**kwargs)
        assert response.status_code==404,(method,path,response.text)
    assert client.get(f"/api/v1/reports/{rid}").status_code==401
    db=SessionLocal()
    try:
        admin=db.scalar(__import__("sqlalchemy").select(User).where(User.email=="admin@careconnect.demo"))
        if not admin:
            admin=User(name="Fictional Admin",email="admin@careconnect.demo",password_hash=pwd.hash("DemoPass123!"),role="admin");db.add(admin);db.commit()
    finally:db.close()
    token=client.post("/api/v1/auth/login",json={"email":"admin@careconnect.demo","password":"DemoPass123!"}).json()["access_token"]
    assert client.get(f"/api/v1/reports/{rid}",headers={"Authorization":f"Bearer {token}"}).status_code==403
    db=SessionLocal()
    try:
        doctor=User(name="Fictional Report Doctor",email=f"doctor-{uuid.uuid4().hex}@example.test",password_hash=pwd.hash("a-long-demo-password"),role="doctor")
        db.add(doctor); db.commit(); email=doctor.email
    finally: db.close()
    doctor_token=client.post("/api/v1/auth/login",json={"email":email,"password":"a-long-demo-password"}).json()["access_token"]
    assert client.get(f"/api/v1/reports/{rid}",headers={"Authorization":f"Bearer {doctor_token}"}).status_code==403
    assert client.delete(f"/api/v1/reports/{rid}",headers=owner).status_code==200


def test_report_retrieval_is_honest_and_operates_without_ollama(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL",raising=False)
    answer=answer_question("Fictional result line: Hemoglobin 13.2 g/dL 12.0-16.0", "What is the hemoglobin value?")
    assert answer["evidence"] and "13.2" in answer["evidence"][0]
    missing=answer_question("Fictional result line: Hemoglobin 13.2 g/dL 12.0-16.0", "What is my vitamin D result?")
    assert "couldn't find" in missing["answer"]
    assert missing["processing_mode"]=="Local rules and retrieval"
    follow_up=answer_question("Glucose 118 mg/dL 70-99 H\nHemoglobin 13.2 g/dL 12.0-16.0", "Is that high?", [{"role":"user","content":"What is the glucose value?"}])
    assert follow_up["evidence"] and "Glucose" in follow_up["evidence"][0]


def test_out_of_range_question_retrieves_report_rows_not_headers_or_legend():
    report=("Test Result Unit Reference range Status\n"
            "WBC 12.4 x10^9/L 4.0-10.0 H\n"
            "Neutrophils 8.4 x10^9/L 1.8-7.5 HIGH\n"
            "Lymphocytes 1.2 x10^9/L 1.0-4.0\n"
            "CRP 16.5 mg/L 0-5 H\n"
            "Platelets 410 x10^9/L 150-400 H\n"
            "Legend: H means HIGH and L means LOW\nReference\n"
            "Test Result Unit Reference range Status\n")
    excerpts=retrieve(report,"Which results are outside the reference ranges?")
    assert len(excerpts)==4
    assert {line.split()[0] for line in excerpts}=={"WBC","Neutrophils","CRP","Platelets"}
    assert all("Legend" not in line and "Reference range Status" not in line for line in excerpts)
    response=answer_question(report,"Which results are outside the reference ranges?")
    assert all(name in response["answer"] for name in ("WBC","Neutrophils","CRP","Platelets"))
    assert "Lymphocytes" not in response["answer"]


def test_report_row_lookup_finds_wbc_neutrophils_lymphocytes_crp_and_platelets():
    report=("Test Result Unit Reference range Status\n"
            "WBC 7.2 x10^9/L 4.0-10.0\n"
            "Neutrophils 4.0 x10^9/L 1.8-7.5\n"
            "Lymphocytes 2.1 x10^9/L 1.0-4.0\n"
            "CRP 2.0 mg/L 0-5\n"
            "Platelets 250 x10^9/L 150-400\n"
            "Legend: H means HIGH and L means LOW\nReference")
    excerpts=retrieve(report,"Find the WBC, neutrophils, lymphocytes, CRP, and platelet values")
    assert {line.split()[0] for line in excerpts}=={"WBC","Neutrophils","Lymphocytes","CRP","Platelets"}


def test_out_of_range_question_reports_insufficient_evidence_when_range_or_flag_missing():
    report="Test Result Unit Reference range Status\nWBC 7.2 x10^9/L\nLegend: H is HIGH\nReference"
    response=answer_question(report,"Which results are outside the reference range?")
    assert response["evidence"]==[]
    assert "couldn't identify" in response["answer"]
    assert "won't infer missing values or ranges" in response["answer"]


def test_report_routes_are_documented_with_request_and_response_schemas():
    schema=client.get("/openapi.json").json()
    assert "/api/v1/reports/upload" in schema["paths"]
    assert "/api/v1/reports/{report_id}/chat" in schema["paths"]
    post=schema["paths"]["/api/v1/reports/{report_id}/chat"]["post"]
    assert post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("ReportQuestion")
    assert post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ReportAnswerOut")

