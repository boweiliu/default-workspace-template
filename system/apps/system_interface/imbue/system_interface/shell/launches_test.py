import pytest

from imbue.system_interface.shell.errors import LaunchUnavailableError
from imbue.system_interface.shell.launches import LaunchPost
from imbue.system_interface.shell.launches import post_launch
from imbue.system_interface.testing import find_free_port


def test_a_launch_no_app_answers_tells_the_person_which_app_by_its_display_name() -> None:
    post = LaunchPost(
        app="buddy",
        display_name="Buddy",
        url=f"http://127.0.0.1:{find_free_port()}/api/intake",
        body={"message": "hi"},
    )

    with pytest.raises(LaunchUnavailableError) as raised:
        post_launch(post)

    assert raised.value.user_facing_message == "Buddy couldn't open that. Try again. If this persists, report a bug."
    assert str(raised.value).startswith("buddy could not be reached for the launch: ")
