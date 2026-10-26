"""A4.2 strict REST RBAC tests against production route definitions; isolated DB."""
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from app.auth_models import User
from app.database import getSession
from app.main import app
from app.routers import deps
from app.services.auth import hash_password
from app.services.state import stateService

PASSWORD='test-a42-example-password'
COMMAND={'deviceId':'greenhouse-01','device':'fan','on':True}
CONFIG={'mode':'MANUAL','tempOnC':30,'tempOffC':28,'humidityOnPct':55,
        'humidityOffPct':65,'lightOnLux':300,'lightOffLux':700}
READS=['/api/state','/api/telemetry','/api/telemetry/latest','/api/config','/api/alerts','/api/commands']

@pytest.fixture()
def client(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        for role in ('admin','operator','viewer'):
            db.add(User(username=f'{role}_a42',email=f'{role}_a42@example.test',
                        password_hash=hash_password(PASSWORD),role=role))
        db.commit()
    def isolated_db():
        with Session(engine) as db: yield db
    app.dependency_overrides[getSession]=isolated_db
    monkeypatch.setattr(deps,'settings',replace(deps.settings,auth_enforcement_enabled=True))
    # Authorized requests stop at offline 409, BEFORE any MQTT publish or DB mutation.
    monkeypatch.setattr(stateService,'onlineFlags',lambda: {})
    try: yield TestClient(app)
    finally:
        app.dependency_overrides.pop(getSession,None)
        engine.dispose()

def login(client,role):
    res=client.post('/api/auth/login',json={'username':f'{role}_a42','password':PASSWORD})
    assert res.status_code==200,res.text
    return res.json()['csrfToken']

@pytest.mark.parametrize('path',READS)
def test_no_cookie_read_is_401(client,path): assert client.get(path).status_code==401

def test_health_public(client): assert client.get('/api/health').status_code==200

@pytest.mark.parametrize('role',['viewer','operator','admin'])
def test_all_roles_read(client,role):
    login(client,role)
    for path in READS: assert client.get(path).status_code==200,(role,path)

@pytest.mark.parametrize('path,payload',[('/api/commands',COMMAND),('/api/config',CONFIG)])
def test_no_cookie_write_is_401(client,path,payload):
    assert client.post(path,json=payload).status_code==401

@pytest.mark.parametrize('path,payload',[('/api/commands',COMMAND),('/api/config',CONFIG)])
def test_viewer_cannot_mutate(client,path,payload):
    csrf=login(client,'viewer')
    assert client.post(path,json=payload,headers={'X-CSRF-Token':csrf}).status_code==403

@pytest.mark.parametrize('path,payload',[('/api/commands',COMMAND),('/api/config',CONFIG)])
def test_operator_without_csrf_blocked(client,path,payload):
    login(client,'operator')
    assert client.post(path,json=payload).status_code==403

@pytest.mark.parametrize('path,payload',[('/api/commands',COMMAND),('/api/config',CONFIG)])
@pytest.mark.parametrize('role',['operator','admin'])
def test_permitted_role_proceeds_to_offline_check(client,path,payload,role):
    csrf=login(client,role)
    res=client.post(path,json=payload,headers={'X-CSRF-Token':csrf})
    assert res.status_code==409,res.text

def test_cross_origin_denied(client):
    csrf=login(client,'admin')
    assert client.post('/api/config',json=CONFIG,headers={'X-CSRF-Token':csrf,
                 'Origin':'https://attacker.example'}).status_code==403

def test_api_key_does_not_bypass_session(client,monkeypatch):
    monkeypatch.setattr(deps,'settings',replace(deps.settings,api_key='legacy-test-key'))
    assert client.post('/api/commands',json=COMMAND,
                       headers={'X-API-Key':'legacy-test-key'}).status_code==401

def test_legacy_demo_mode_still_works(client,monkeypatch):
    monkeypatch.setattr(deps,'settings',replace(deps.settings,auth_enforcement_enabled=False))
    assert client.get('/api/state').status_code==200
