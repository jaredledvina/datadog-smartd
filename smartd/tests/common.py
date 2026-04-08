import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(HERE, 'fixtures')

INSTANCE = {
    'smartd_state_dir': FIXTURE_DIR,
    'file_pattern': 'smartd.*.state',
}

CHECK_NAME = 'smartd'

HEALTHY_MODEL = 'ACME_DISK4000'
HEALTHY_SERIAL = 'SN123456789ABC'
HEALTHY_TAGS = ['device_model:{}'.format(HEALTHY_MODEL), 'serial_number:{}'.format(HEALTHY_SERIAL)]

DEGRADED_MODEL = 'ACME_DISK4000'
DEGRADED_SERIAL = 'SN987654321XYZ'
DEGRADED_TAGS = ['device_model:{}'.format(DEGRADED_MODEL), 'serial_number:{}'.format(DEGRADED_SERIAL)]
