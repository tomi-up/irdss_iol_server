from sqlalchemy import Column, Integer, String, Float
from app.database.db_connection import Base


class PatientRecords(Base):
    __tablename__ = "patient_record"
    id = Column(Integer, primary_key=True, index=True)
    fhir_id = Column(String, unique=True, index=True)
    age = Column(Integer)
    salary = Column(Float)
    severity = Column(Integer)
    latitude = Column(Float)
    longitude = Column(Float)
    fitness = Column(Integer)

