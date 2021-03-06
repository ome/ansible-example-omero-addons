import json
import os
import pytest
from time import sleep, time
import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')


OMERO = '/opt/omero/server/OMERO.server/bin/omero'
ROOT_PASSWORD = 'ChangeMe'


def test_db_running_and_enabled(host):
    service_centos = host.service('postgresql-11')
    service_ubuntu = host.service('postgresql@11-main')
    assert service_centos.is_running or service_ubuntu.is_running
    assert service_centos.is_enabled or service_ubuntu.is_enabled


def test_srv_running_and_enabled(host):
    service = host.service('omero-server')
    assert service.is_running
    assert service.is_enabled


def test_omero_login(host):
    # Ubuntu sudo doesn't set HOME so it tries to write to /root
    env = 'OMERO_USERDIR=/tmp/omero-{}'.format(time())
    with host.sudo('omero-server'):
        host.check_output(
            '%s %s login -C -s localhost -u root -w %s' % (
                env, OMERO, ROOT_PASSWORD))


@pytest.mark.parametrize('name', ['omero-web', 'nginx'])
def test_services_running_and_enabled(host, name):
    service = host.service(name)
    assert service.is_running
    assert service.is_enabled


def test_omero_web_first_page(host):
    out1 = host.check_output('curl -fsL http://localhost')
    assert 'WEBCLIENT.active_group_id' in out1
    out2 = host.check_output('curl -fsL http://localhost/webclient/login')
    assert 'omero:4064' in out2


def get_cookie(cookietxt, name):
    for line in cookietxt.splitlines():
        tokens = line.split()
        try:
            if tokens[5] == name:
                return tokens[6]
        except IndexError:
            pass


# https://github.com/openmicroscopy/omero-grid-docker/blob/0.1.0/test_login.sh
def test_omero_web_login(host):
    LOGIN_URL = 'http://localhost/webclient/login/'
    CURL = 'curl -f -i -k -s -c cookies.txt -b cookies.txt -e %s' % LOGIN_URL

    for i in range(60):
        sleep(2)
        host.check_output('%s %s' % (CURL, LOGIN_URL))
        csrf = get_cookie(host.file('cookies.txt').content_string, 'csrftoken')
        if csrf:
            break
    assert csrf

    data = '&'.join([
        'csrfmiddlewaretoken=%s' % csrf,
        'username=root',
        'password=%s' % ROOT_PASSWORD,
        'server=1',
        'url=%2Fwebclient%2F',
        ])

    for i in range(60):
        sleep(2)
        host.check_output('%s -d "%s" -X POST %s' % (
            CURL, data, LOGIN_URL))
        sessionid = get_cookie(
            host.file('cookies.txt').content_string, 'sessionid')
        if sessionid:
            break
    assert sessionid


def test_omero_web_public(host):
    out = host.check_output(
        'curl -f http://localhost/webclient/api/containers/')
    r = json.loads(out)
    assert r['screens'] == []
    assert r['plates'] == []
    assert r['projects'] == []
    assert r['datasets'] == []
