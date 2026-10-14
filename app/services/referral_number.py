"""
Human-readable referral numbers in the form REF-YYYYMM-NNNNN.

The sequence restarts every month (Philippine time, UTC+8 with no DST) and is
shared network-wide, since IRDSS is the single issuer. The counter row is
incremented with one atomic INSERT ... ON CONFLICT DO UPDATE ... RETURNING, so
concurrent referrals can never receive the same number. Because it runs inside
the caller's transaction, a referral that fails and rolls back also releases
its number.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.referral_model import ReferralNumberSequence

PHILIPPINE_TIME = timezone(timedelta(hours=8))
REFERRAL_NUMBER_PREFIX = "REF"


def referral_number_period(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(PHILIPPINE_TIME).strftime("%Y%m")


def format_referral_number(period: str, value: int) -> str:
    return f"{REFERRAL_NUMBER_PREFIX}-{period}-{value:05d}"


def next_referral_number(db: Session, now: Optional[datetime] = None) -> str:
    period = referral_number_period(now)
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else postgresql_insert
    statement = (
        insert(ReferralNumberSequence)
        .values(period=period, last_value=1)
        .on_conflict_do_update(
            index_elements=[ReferralNumberSequence.period],
            set_={"last_value": ReferralNumberSequence.last_value + 1},
        )
        .returning(ReferralNumberSequence.last_value)
    )
    value = db.execute(statement).scalar_one()
    return format_referral_number(period, value)
