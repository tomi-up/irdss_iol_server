"""restructure hospital_resources into facilities, add facility_users and facility_capabilities

Revision ID: c1f8a92e4d6b
Revises: 9a3d5e7c2f1b
Create Date: 2026-08-11 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f8a92e4d6b'
down_revision: Union[str, Sequence[str], None] = '9a3d5e7c2f1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename table + core identity columns
    op.rename_table('hospital_resources', 'facilities')
    op.alter_column('facilities', 'hospital_name', new_column_name='facility_name')
    op.alter_column('facilities', 'hospital_level', new_column_name='facility_type')

    # 2. Capture inventory data into facility_capabilities before dropping the old columns
    op.create_table(
        'facility_capabilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('facility_id', sa.Integer(), nullable=False),
        sa.Column('authorized_bed_capacity', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('functional_beds', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('has_icu', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_nicu', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_er_trauma', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_delivery_room', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_hemodialysis', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_blood_bank', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_ct_mri', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_cardiologist', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_obgyn', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_neurologist', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('has_general_surgeon', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['facility_id'], ['facilities.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_facility_capabilities_facility_id'), 'facility_capabilities', ['facility_id'], unique=True)
    op.create_index(op.f('ix_facility_capabilities_id'), 'facility_capabilities', ['id'], unique=False)

    # Carry forward existing available_beds/emergency_equipment/medical_equipment/
    # communication_systems into their new DOH-style homes so already-seeded facilities
    # don't silently drop out of routing_filter.py's candidate matching.
    op.execute("""
        INSERT INTO facility_capabilities (
            facility_id, authorized_bed_capacity, functional_beds,
            has_er_trauma, has_icu
        )
        SELECT id, COALESCE(available_beds, 0), COALESCE(available_beds, 0),
               COALESCE(emergency_equipment, false), COALESCE(medical_equipment, false)
        FROM facilities
    """)

    # 3. Drop the old inventory/environment columns now that their data lives above
    op.drop_column('facilities', 'hospital_environment')
    op.drop_column('facilities', 'available_beds')
    op.drop_column('facilities', 'emergency_equipment')
    op.drop_column('facilities', 'medical_equipment')
    op.drop_column('facilities', 'communication_systems')

    # 4. Add the new Facility Information / Location / Contact / Licensing / System columns
    op.add_column('facilities', sa.Column('facility_code', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('ownership', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('facility_head', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('region', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('province', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('municipality', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('barangay', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('address', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('contact_number', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('email', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('lto_number', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('lto_type', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('lto_issue_date', sa.Date(), nullable=True))
    op.add_column('facilities', sa.Column('lto_expiration_date', sa.Date(), nullable=True))
    op.add_column('facilities', sa.Column('lto_status', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('lto_file_path', sa.String(), nullable=True))
    op.add_column('facilities', sa.Column('facility_status', sa.String(), nullable=True, server_default='Active'))

    # 5. Backfill facility_code for any existing rows, then enforce uniqueness
    op.execute("UPDATE facilities SET facility_code = 'FAC-' || LPAD(id::text, 6, '0') WHERE facility_code IS NULL")
    op.create_index(op.f('ix_facilities_facility_code'), 'facilities', ['facility_code'], unique=True)

    # 6. facility_users
    op.create_table(
        'facility_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('facility_id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='FACILITY_ADMIN'),
        sa.Column('status', sa.String(), nullable=False, server_default='Active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['facility_id'], ['facilities.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_facility_users_id'), 'facility_users', ['id'], unique=False)
    op.create_index(op.f('ix_facility_users_facility_id'), 'facility_users', ['facility_id'], unique=False)
    op.create_index(op.f('ix_facility_users_username'), 'facility_users', ['username'], unique=True)

    # 7. Rename the index that used to track hospital_name (SQLAlchemy names it after the
    #    original table+column; make sure the new name matches what the ORM expects going forward)
    op.execute('ALTER INDEX IF EXISTS ix_hospital_resources_hospital_name RENAME TO ix_facilities_facility_name')
    op.execute('ALTER INDEX IF EXISTS ix_hospital_resources_id RENAME TO ix_facilities_id')


def downgrade() -> None:
    op.execute('ALTER INDEX IF EXISTS ix_facilities_facility_name RENAME TO ix_hospital_resources_hospital_name')
    op.execute('ALTER INDEX IF EXISTS ix_facilities_id RENAME TO ix_hospital_resources_id')

    op.drop_index(op.f('ix_facility_users_username'), table_name='facility_users')
    op.drop_index(op.f('ix_facility_users_facility_id'), table_name='facility_users')
    op.drop_index(op.f('ix_facility_users_id'), table_name='facility_users')
    op.drop_table('facility_users')

    op.drop_index(op.f('ix_facilities_facility_code'), table_name='facilities')

    op.add_column('facilities', sa.Column('communication_systems', sa.Boolean(), nullable=True))
    op.add_column('facilities', sa.Column('medical_equipment', sa.Boolean(), nullable=True))
    op.add_column('facilities', sa.Column('emergency_equipment', sa.Boolean(), nullable=True))
    op.add_column('facilities', sa.Column('available_beds', sa.Integer(), nullable=True))
    op.add_column('facilities', sa.Column('hospital_environment', sa.String(), nullable=True))

    op.execute("""
        UPDATE facilities f SET
            available_beds = fc.functional_beds,
            emergency_equipment = fc.has_er_trauma,
            medical_equipment = fc.has_icu,
            communication_systems = false
        FROM facility_capabilities fc
        WHERE fc.facility_id = f.id
    """)

    op.drop_column('facilities', 'facility_status')
    op.drop_column('facilities', 'lto_file_path')
    op.drop_column('facilities', 'lto_status')
    op.drop_column('facilities', 'lto_expiration_date')
    op.drop_column('facilities', 'lto_issue_date')
    op.drop_column('facilities', 'lto_type')
    op.drop_column('facilities', 'lto_number')
    op.drop_column('facilities', 'email')
    op.drop_column('facilities', 'contact_number')
    op.drop_column('facilities', 'address')
    op.drop_column('facilities', 'barangay')
    op.drop_column('facilities', 'municipality')
    op.drop_column('facilities', 'province')
    op.drop_column('facilities', 'region')
    op.drop_column('facilities', 'facility_head')
    op.drop_column('facilities', 'ownership')
    op.drop_column('facilities', 'facility_code')

    op.drop_index(op.f('ix_facility_capabilities_id'), table_name='facility_capabilities')
    op.drop_index(op.f('ix_facility_capabilities_facility_id'), table_name='facility_capabilities')
    op.drop_table('facility_capabilities')

    op.alter_column('facilities', 'facility_type', new_column_name='hospital_level')
    op.alter_column('facilities', 'facility_name', new_column_name='hospital_name')
    op.rename_table('facilities', 'hospital_resources')
