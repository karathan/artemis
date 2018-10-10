from flask import Blueprint, render_template
from flask import redirect, request, jsonify
from flask_security.decorators import roles_required, roles_accepted
from webapp.data.models import User, Role
from webapp.templates.forms import CheckboxForm, ApproveUserForm, MakeAdminForm, DeleteUserForm
from webapp.core import app
from webapp.core.modules import Modules_status
from webapp.core.actions import New_config
from webapp.core.fetch_config import fetch_all_config_timestamps
import logging
import time

log = logging.getLogger('webapp_logger')

admin = Blueprint('admin', __name__, template_folder='templates')


@admin.route('/', methods=['GET', 'POST'])
@roles_required('admin')
def default():
    return redirect("admin/system")


@admin.route('/system', methods=['GET', 'POST'])
@roles_required('admin')
def index():
    # log info
    form = CheckboxForm()
    app.config['configuration'].get_newest_config()

    app.config['module_control'].refresh_status_all()
    app.config['module_status'] = app.config['module_control'].get_response_all()

    module_handler = Modules_status()

    if form.validate_on_submit():
        if form.monitor.data:
            module_handler.call('monitor', 'start')
            app.config['module_control'].force_status_update()
        else:
            module_handler.call('monitor', 'stop')
            app.config['module_control'].force_status_update()
        if form.detector.data:
            module_handler.call('detection', 'start')
            app.config['module_control'].force_status_update()
        else:
            module_handler.call('detection', 'stop')
            app.config['module_control'].force_status_update()
        if form.mitigator.data:
            module_handler.call('mitigation', 'start')
            app.config['module_control'].force_status_update()
        else:
            module_handler.call('mitigation', 'stop')
            app.config['module_control'].force_status_update()
        time.sleep(1)
    else:
        if app.config['module_status']['monitor']['status'] == 'up':
            form.monitor.data = True
        else:
            form.monitor.data = False
        if app.config['module_status']['detection']['status'] == 'up':
            form.detector.data = True
        else:
            form.detector.data = False
        if app.config['module_status']['mitigation']['status'] == 'up':
            form.mitigator.data = True
        else:
            form.mitigator.data = False

    return render_template('system.htm',
                           form=form,
                           config=app.config['configuration'].get_raw_config(),
                           config_timestamp=app.config['configuration'].get_config_last_modified())


@admin.route('/config/', methods=['POST'])
@roles_required('admin')
def handle_new_config():
    # log info
    app.config['configuration'].get_newest_config()
    old_config = app.config['configuration'].get_raw_config()
    config_modify = New_config()
    new_config = request.values.get('new_config')
    response, success = config_modify.send(new_config, old_config)

    if success:
        return jsonify(
            {'status': 'success', 'data': new_config, 'response': response})
    else:
        return jsonify(
            {'status': 'fail', 'data': new_config, 'response': response})


@admin.route('/user_management', methods=['GET'])
@roles_required('admin')
def user_management():
    # log info
    _pending_users_form = ApproveUserForm()

    _pending_users_list = []
    _pending_users = User.query.filter(User.roles.any(Role.id.in_(
        [(app.security.datastore.find_role("pending")).id]))).all()

    for _pending_user in _pending_users:
        _pending_users_list.append((_pending_user.id, _pending_user.username))

    _pending_users_form.user_to_approve.choices = _pending_users_list

    _users_to_promote_to_admin = MakeAdminForm()
    _users_list = []
    _users = User.query.filter(User.roles.any(Role.id.in_(
        [(app.security.datastore.find_role("user")).id]))).all()

    for _user in _users:
        _users_list.append((_user.id, _user.username))

    _users_to_promote_to_admin.user_to_make_admin.choices = _users_list

    _users_to_delete = DeleteUserForm()
    _users_to_delete.user_to_delete.choices = _pending_users_list + _users_list

    user_list = []
    _admins = User.query.filter(User.roles.any(Role.id.in_(
        [(app.security.datastore.find_role("admin")).id]))).all()

    for user in _pending_users:
        user_list.append(
            (
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'pending',
                    'last_login_at': user.last_login_at.timestamp()
                }
            )
        )

    for user in _users:
        user_list.append(
            (
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'user',
                    'last_login_at': user.last_login_at.timestamp()
                }
            )
        )
    for user in _admins:
        user_list.append(
            (
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': 'admin',
                    'last_login_at': user.last_login_at.timestamp()
                }
            )
        )

    return render_template('user_management.htm',
                           users_to_approve_form=_pending_users_form,
                           users_to_make_admin_form=_users_to_promote_to_admin,
                           users_to_delete_form=_users_to_delete,
                           users_list=user_list
                           )


@admin.route('/config_comparison', methods=['GET'])
@roles_accepted('admin', 'user')
def config_comparison():
    # log info
    _configs = fetch_all_config_timestamps()
    return render_template('config_comparison.htm',
                           configs=list(reversed(_configs)))
