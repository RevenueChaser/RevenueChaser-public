"""Which builder runs reach the phone (core/notify.py, avo 17 Nov 2026): a pressed Build either way, the hourly
pass only on failure. The hourly pass queues requests too, by due.REQUESTED_BY."""
from RevenueChaser.rcdata.build import base, due


def test_a_schedule_request_is_not_pressed():
    assert base._pressed({"id": 7, "requested_by": due.REQUESTED_BY}) is False


def test_a_person_request_is_pressed():
    assert base._pressed({"id": 7, "requested_by": "dashboard"}) is True


def test_no_request_is_not_pressed():
    assert base._pressed({}) is False
