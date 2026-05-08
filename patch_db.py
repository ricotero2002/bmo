from airflow.settings import Session
from sqlalchemy import text
s = Session()
try:
    s.execute(text("ALTER TABLE session ALTER COLUMN expiry TYPE TIMESTAMP WITHOUT TIME ZONE USING expiry AT TIME ZONE 'UTC'"))
    s.commit()
    print('✅ Columna expiry convertida a TIMESTAMP WITHOUT TIME ZONE con éxito')
except Exception as e:
    print(f'❌ Error: {e}')
    s.rollback()
finally:
    s.close()
