from unittest.mock import patch

from backup_tool.cloud.rclone_config import (
    RcloneConfigResponse,
    continue_remote_configuration,
    start_remote_configuration,
)


def test_start_remote_configuration_parses_rclone_question():
    stdout = """{
        "State": "client_id_set",
        "Option": {
            "Name": "client_id",
            "FieldName": "",
            "Help": "Google Application Client Id",
            "Default": "",
            "Value": null,
            "Examples": [],
            "Hide": 0,
            "Required": true,
            "IsPassword": false,
            "NoPrefix": false,
            "Advanced": false,
            "Sensitive": false,
            "DefaultStr": "",
            "ValueStr": "",
            "Exclusive": false,
            "Type": "string"
        },
        "Error": "",
        "Result": ""
    }"""

    completed = type(
        "Completed",
        (),
        {"stdout": stdout},
    )()

    with patch(
        "backup_tool.cloud.rclone_config.find_rclone",
        return_value="rclone",
    ), patch(
        "backup_tool.cloud.rclone_config.subprocess.run",
        return_value=completed,
    ) as run:
        response = start_remote_configuration(
            remote_name="test_remote",
            backend_type="drive",
        )

    assert isinstance(response, RcloneConfigResponse)
    assert response.state == "client_id_set"
    assert response.option is not None
    assert response.option.name == "client_id"
    assert response.option.required is True
    assert response.option.value_type == "string"

    assert response.option.field_name == ""
    assert response.option.hide == 0
    assert response.option.advanced is False
    assert response.option.sensitive is False
    assert response.option.default_str == ""
    assert response.option.value_str == ""
    assert response.option.no_prefix is False

    command = run.call_args.args[0]
    assert command == [
        "rclone",
        "config",
        "create",
        "test_remote",
        "drive",
        "--non-interactive",
    ]


def test_continue_remote_configuration_from_client_warning():
    stdout = """{
        "State": "client_id_set",
        "Option": {
            "Name": "client_id",
            "Help": "Google Application Client Id",
            "Default": "",
            "Value": null,
            "Examples": [],
            "Hide": 0,
            "Required": true,
            "IsPassword": false,
            "NoPrefix": false,
            "Advanced": false,
            "Sensitive": false,
            "DefaultStr": "",
            "ValueStr": "",
            "Exclusive": false,
            "Type": "string"
        },
        "Error": "",
        "Result": ""
    }"""

    completed = type(
        "Completed",
        (),
        {"stdout": stdout},
    )()

    with patch(
        "backup_tool.cloud.rclone_config.find_rclone",
        return_value="rclone",
    ), patch(
        "backup_tool.cloud.rclone_config.subprocess.run",
        return_value=completed,
    ) as run:
        response = continue_remote_configuration(
            remote_name="test_remote",
            backend_type="drive",
            state="client_id_warning",
            result="false",
        )

    assert response.state == "client_id_set"
    assert response.option is not None
    assert response.option.name == "client_id"

    command = run.call_args.args[0]
    assert command == [
        "rclone",
        "config",
        "update",
        "test_remote",
        "--continue",
        "--state",
        "client_id_warning",
        "--result",
        "false",
    ]


def test_continue_remote_configuration_from_client_id():
    stdout = """{
        "State": "client_secret_set",
        "Option": {
            "Name": "client_secret",
            "Help": "Google Application Client Secret",
            "Default": "",
            "Value": null,
            "Examples": [],
            "Hide": 0,
            "Required": true,
            "IsPassword": true,
            "NoPrefix": false,
            "Advanced": false,
            "Sensitive": true,
            "DefaultStr": "",
            "ValueStr": "",
            "Exclusive": false,
            "Type": "string"
        },
        "Error": "",
        "Result": ""
    }"""

    completed = type(
        "Completed",
        (),
        {"stdout": stdout},
    )()

    with patch(
        "backup_tool.cloud.rclone_config.find_rclone",
        return_value="rclone",
    ), patch(
        "backup_tool.cloud.rclone_config.subprocess.run",
        return_value=completed,
    ) as run:
        response = continue_remote_configuration(
            remote_name="test_remote",
            backend_type="drive",
            state="client_id_set",
            result="test-client-id",
        )

    assert response.state == "client_secret_set"
    assert response.option is not None
    assert response.option.name == "client_secret"
    assert response.option.is_password is True
    assert response.option.sensitive is True

    command = run.call_args.args[0]
    assert command == [
        "rclone",
        "config",
        "update",
        "test_remote",
        "--continue",
        "--state",
        "client_id_set",
        "--result",
        "test-client-id",
    ]


def test_rclone_config_session_start_updates_state():
    from backup_tool.cloud.rclone_config import RcloneConfigSession

    response = RcloneConfigResponse(
        state="client_id_warning",
        option=None,
        error="",
        result="",
    )

    with patch(
        "backup_tool.cloud.rclone_config.start_remote_configuration",
        return_value=response,
    ) as start:
        session = RcloneConfigSession(
            remote_name="test_remote",
            backend_type="drive",
        )

        result = session.start()

    assert result is response
    assert session.state == "client_id_warning"
    assert session.completed is False
    start.assert_called_once_with(
        remote_name="test_remote",
        backend_type="drive",
        timeout_seconds=None,
    )


def test_rclone_config_session_answer_updates_state():
    from backup_tool.cloud.rclone_config import RcloneConfigSession

    start_response = RcloneConfigResponse(
        state="client_id_warning",
        option=None,
        error="",
        result="",
    )
    next_response = RcloneConfigResponse(
        state="client_id_set",
        option=None,
        error="",
        result="",
    )

    with patch(
        "backup_tool.cloud.rclone_config.start_remote_configuration",
        return_value=start_response,
    ), patch(
        "backup_tool.cloud.rclone_config.continue_remote_configuration",
        return_value=next_response,
    ) as continue_config:
        session = RcloneConfigSession(
            remote_name="test_remote",
            backend_type="drive",
        )

        session.start()
        result = session.answer("false")

    assert result is next_response
    assert session.state == "client_id_set"
    assert session.completed is False
    continue_config.assert_called_once_with(
        remote_name="test_remote",
        backend_type="drive",
        state="client_id_warning",
        result="false",
        timeout_seconds=None,
    )


def test_rclone_oauth_process_start_builds_command():
    from backup_tool.cloud.rclone_config import RcloneOAuthProcess

    process_mock = type(
        "Process",
        (),
        {
            "poll": lambda self: None,
        },
    )()

    with patch(
        "backup_tool.cloud.rclone_config.find_rclone",
        return_value="rclone",
    ), patch(
        "backup_tool.cloud.rclone_config.subprocess.Popen",
        return_value=process_mock,
    ) as popen:
        oauth = RcloneOAuthProcess(
            remote_name="test_remote",
            backend_type="drive",
        )

        result = oauth.start(
            state="*oauth-islocal,teamdrive,oauth,",
            result="true",
        )

    assert result is process_mock
    assert oauth.process is process_mock
    assert oauth.running is True

    command = popen.call_args.args[0]
    assert command == [
        "rclone",
        "config",
        "update",
        "test_remote",
        "--continue",
        "--state",
        "*oauth-islocal,teamdrive,oauth,",
        "--result",
        "true",
    ]

    assert popen.call_args.kwargs["text"] is True
    assert popen.call_args.kwargs["stdout"] is not None
    assert popen.call_args.kwargs["stderr"] is not None
