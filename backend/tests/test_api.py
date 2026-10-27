import uuid
from datetime import date, timedelta, datetime
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, SessionLocal, User, Specialty, Doctor, Availability, Document, pwd

client=TestClient(app)

def patient_session():
    email=f"{uuid.uuid4().hex}@example.test"
    response=client.post('/api/v1/auth/register',json={'name':'Synthetic Test Patient','email':email,'password':'a-long-demo-password'})
    assert response.status_code==201
    token=client.post('/api/v1/auth/login',json={'email':email,'password':'a-long-demo-password'}).json()['access_token']
    return email,{'Authorization':f'Bearer {token}'}

def test_register_login_and_me():
    email=f"{uuid.uuid4().hex}@example.test"
    created=client.post('/api/v1/auth/register',json={'name':'Sample Patient','email':email,'password':'a-long-demo-password'})
    assert created.status_code==201
    login=client.post('/api/v1/auth/login',json={'email':email,'password':'a-long-demo-password'})
    assert login.status_code==200
    assert client.get('/api/v1/auth/me',headers={'Authorization':f"Bearer {login.json()['access_token']}"}).json()['email']==email
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'incorrect'}).status_code==401

def test_patient_role_is_enforced():
    email=f"{uuid.uuid4().hex}@example.test"
    client.post('/api/v1/auth/register',json={'name':'Role Test','email':email,'password':'a-long-demo-password'})
    token=client.post('/api/v1/auth/login',json={'email':email,'password':'a-long-demo-password'}).json()['access_token']
    assert client.get('/api/v1/admin/overview',headers={'Authorization':f'Bearer {token}'}).status_code==403

def test_booking_available_slot_and_double_booking():
    db=SessionLocal()
    suffix=uuid.uuid4().hex
    try:
        spec=Specialty(name='Test '+suffix); db.add(spec); db.flush()
        doctor=User(name='Test Doctor',email=f'doc-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='doctor'); patient=User(name='Test Patient',email=f'pat-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='patient'); db.add_all([doctor,patient]); db.flush()
        db.add(Doctor(id=doctor.id,specialty_id=spec.id)); day=date.today()+timedelta(days=5); db.add(Availability(doctor_id=doctor.id,day=day,hour=10)); db.commit()
        token=client.post('/api/v1/auth/login',json={'email':patient.email,'password':'a-long-demo-password'}).json()['access_token']; headers={'Authorization':f'Bearer {token}'}
        data={'doctor_id':doctor.id,'starts_at':datetime.combine(day,datetime.min.time()).replace(hour=10).isoformat(),'reason':'Demo visit'}
        assert client.post('/api/v1/appointments',json=data,headers=headers).status_code==201
        assert client.post('/api/v1/appointments',json=data,headers=headers).status_code==409
        invalid={**data,'starts_at':datetime.combine(date.today()-timedelta(days=1),datetime.min.time()).isoformat()}
        assert client.post('/api/v1/appointments',json=invalid,headers=headers).status_code==422
        off_slot={**data,'starts_at':datetime.combine(day,datetime.min.time()).replace(hour=10,minute=30).isoformat()}
        assert client.post('/api/v1/appointments',json=off_slot,headers=headers).status_code==422
    finally:
        db.close()

def test_registration_validation_and_duplicate_email():
    email=f"{uuid.uuid4().hex}@example.test"
    assert client.post('/api/v1/auth/register',json={'name':'Tiny','email':email,'password':'short'}).status_code==422
    body={'name':'Auth Test','email':email,'password':'a-long-demo-password'}
    assert client.post('/api/v1/auth/register',json=body).status_code==201
    assert client.post('/api/v1/auth/register',json=body).status_code==409
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'wrong-password'}).status_code==401

def test_private_appointment_ownership_and_doctor_authorization():
    db=SessionLocal(); suffix=uuid.uuid4().hex
    try:
        spec=Specialty(name='Ownership '+suffix); db.add(spec); db.flush()
        doctor=User(name='Authorized Clinician',email=f'doc-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='doctor'); patient=User(name='Owner Patient',email=f'pat-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='patient'); outsider=User(name='Other Patient',email=f'other-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='patient'); db.add_all([doctor,patient,outsider]); db.flush()
        db.add(Doctor(id=doctor.id,specialty_id=spec.id)); day=date.today()+timedelta(days=7); db.add(Availability(doctor_id=doctor.id,day=day,hour=11)); db.commit()
        body={'doctor_id':doctor.id,'starts_at':datetime.combine(day,datetime.min.time()).replace(hour=11).isoformat()}
        pt=client.post('/api/v1/auth/login',json={'email':patient.email,'password':'a-long-demo-password'}).json()['access_token']; ot=client.post('/api/v1/auth/login',json={'email':outsider.email,'password':'a-long-demo-password'}).json()['access_token']; dt=client.post('/api/v1/auth/login',json={'email':doctor.email,'password':'a-long-demo-password'}).json()['access_token']
        booked=client.post('/api/v1/appointments',json=body,headers={'Authorization':f'Bearer {pt}'}); aid=booked.json()['id']
        assert client.patch(f'/api/v1/appointments/{aid}/status',json={'status':'cancelled'},headers={'Authorization':f'Bearer {ot}'}).status_code==403
        assert client.patch(f'/api/v1/appointments/{aid}/status',json={'status':'confirmed'},headers={'Authorization':f'Bearer {dt}'}).status_code==200
    finally: db.close()

def test_pdf_extraction_and_document_ownership():
    import fitz
    email,headers=patient_session(); doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),'Fictional report date 2026-04-02 blood pressure review'); payload=doc.tobytes(); doc.close()
    response=client.post('/api/v1/documents',headers=headers,files={'file':('sample.pdf',payload,'application/pdf')})
    assert response.status_code==201
    doc_id=response.json()['id']; db=SessionLocal()
    try: assert 'blood pressure' in db.get(Document,doc_id).extracted_text.lower()
    finally: db.close()
    _,outsider_headers=patient_session()
    assert client.post(f'/api/v1/documents/{doc_id}/analyze',headers=outsider_headers).status_code==404
    assert client.post(f'/api/v1/documents/{doc_id}/analyze',headers=headers).status_code==200
    assert client.delete(f'/api/v1/documents/{doc_id}',headers=headers).status_code==200

def test_no_show_prediction_and_input_validation():
    db=SessionLocal()
    try:
        admin=db.scalar(select(User).where(User.email=='admin@careconnect.demo'))
        if admin is None:
            admin=User(name='Demo Administrator',email='admin@careconnect.demo',password_hash=pwd.hash('DemoPass123!'),role='admin'); db.add(admin); db.commit()
    finally: db.close()
    token=client.post('/api/v1/auth/login',json={'email':'admin@careconnect.demo','password':'DemoPass123!'}).json()['access_token']; headers={'Authorization':f'Bearer {token}'}
    result=client.post('/api/v1/ml/no-show/predict',headers=headers,json={'lead_days':8,'weekday':2,'hour':10})
    assert result.status_code==200 and 0<=result.json()['risk']<=1
    metrics=client.get('/api/v1/ml/metrics',headers=headers)
    assert metrics.status_code==200 and 'baseline' in metrics.json() and 'baseline_roc_auc' in metrics.json()['metrics']
    assert client.post('/api/v1/ml/no-show/predict',headers=headers,json={'lead_days':-1,'weekday':2,'hour':10}).status_code==422

def test_admin_doctor_creation_and_account_deactivation():
    db=SessionLocal()
    try:
        admin=db.scalar(select(User).where(User.email=='admin@careconnect.demo'))
        if admin is None:
            admin=User(name='Demo Administrator',email='admin@careconnect.demo',password_hash=pwd.hash('DemoPass123!'),role='admin'); db.add(admin); db.commit()
        specialty=db.scalar(select(Specialty))
        if specialty is None:
            specialty=Specialty(name='Admin Test Specialty'); db.add(specialty); db.commit(); db.refresh(specialty)
        specialty_id=specialty.id
    finally: db.close()
    token=client.post('/api/v1/auth/login',json={'email':'admin@careconnect.demo','password':'DemoPass123!'}).json()['access_token']; headers={'Authorization':f'Bearer {token}'}
    suffix=uuid.uuid4().hex
    created=client.post('/api/v1/admin/doctors',headers=headers,json={'name':'Managed Demo Clinician','email':f'managed-{suffix}@example.test','password':'a-long-demo-password','specialty_id':specialty_id,'experience':4,'fee':50,'bio':'Fictional test clinician'})
    assert created.status_code==201
    _,patient_headers=patient_session()
    patient=client.get('/api/v1/auth/me',headers=patient_headers).json()
    assert client.patch(f"/api/v1/admin/users/{patient['id']}/status",headers=headers,json={'active':False}).status_code==200
    assert client.get('/api/v1/auth/me',headers=patient_headers).status_code==401

def test_consultation_notes_and_notifications_are_scoped():
    db=SessionLocal(); suffix=uuid.uuid4().hex
    try:
        spec=Specialty(name='Notes '+suffix); db.add(spec); db.flush()
        doctor=User(name='Note Clinician',email=f'doc-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='doctor'); patient=User(name='Note Patient',email=f'pat-{suffix}@example.test',password_hash=pwd.hash('a-long-demo-password'),role='patient'); db.add_all([doctor,patient]); db.flush(); db.add(Doctor(id=doctor.id,specialty_id=spec.id)); day=date.today()+timedelta(days=8); db.add(Availability(doctor_id=doctor.id,day=day,hour=12)); db.commit()
        pt=client.post('/api/v1/auth/login',json={'email':patient.email,'password':'a-long-demo-password'}).json()['access_token']; dt=client.post('/api/v1/auth/login',json={'email':doctor.email,'password':'a-long-demo-password'}).json()['access_token']
        a=client.post('/api/v1/appointments',json={'doctor_id':doctor.id,'starts_at':datetime.combine(day,datetime.min.time()).replace(hour=12).isoformat()},headers={'Authorization':f'Bearer {pt}'}).json(); aid=a['id']
        assert client.patch(f'/api/v1/appointments/{aid}/status',json={'status':'confirmed'},headers={'Authorization':f'Bearer {dt}'}).status_code==200
        note=client.put(f'/api/v1/appointments/{aid}/notes',json={'content':'Fictional consultation note','follow_up':(day+timedelta(days=10)).isoformat()},headers={'Authorization':f'Bearer {dt}'})
        assert note.status_code==200
        assert client.get(f'/api/v1/appointments/{aid}/notes',headers={'Authorization':f'Bearer {pt}'}).json()['content']=='Fictional consultation note'
        notifications=client.get('/api/v1/notifications',headers={'Authorization':f'Bearer {pt}'}).json()
        assert notifications
        outsider_headers=patient_session()[1]
        assert client.get(f'/api/v1/appointments/{aid}/notes',headers=outsider_headers).status_code==404
        assert client.patch(f"/api/v1/notifications/{notifications[0]['id']}/read",headers=outsider_headers).status_code==404
    finally: db.close()
