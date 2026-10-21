"""Runtime regression test for the shared latest-assignment summary query."""
from datetime import date


def test_latest_assignment_summary_returns_destination_governorate_and_closed_state(app):
    from employee_movements.assignments import latest_assignment_summaries
    from employee_movements.extensions import db
    from employee_movements.models import Branch, Employee, Governorate, Movement, User

    with app.app_context():
        actor = User.query.filter_by(username="admin").first()
        assert actor is not None
        home_gov = Governorate(name="محافظة اختبار أصلية", is_active=True)
        destination_gov = Governorate(name="محافظة اختبار الوجهة", is_active=True)
        db.session.add_all([home_gov, destination_gov])
        db.session.flush()
        home_branch = Branch(governorate_id=home_gov.id, name="فرع الموظف", code="T-SRC", is_active=True)
        old_destination = Branch(governorate_id=home_gov.id, name="وجهة أقدم", code="T-OLD", is_active=True)
        new_destination = Branch(governorate_id=destination_gov.id, name="وجهة أحدث", code="T-NEW", is_active=True)
        db.session.add_all([home_branch, old_destination, new_destination])
        db.session.flush()
        employee = Employee(
            full_name="موظف اختبار ملخص الانتداب",
            branch_id=home_branch.id,
            job_title="اختبار",
            job_code="T-EMP-57",
            is_active=True,
        )
        db.session.add(employee)
        db.session.flush()
        db.session.add_all([
            Movement(
                employee_id=employee.id,
                movement_type="انتداب",
                destination_branch_id=old_destination.id,
                from_date=date(2026, 1, 1),
                to_date=date(2026, 1, 5),
                status="مسجلة",
                is_active=True,
                created_by=actor.id,
                assignment_state="ساري",
                mission_state="تحت التحرير",
            ),
            Movement(
                employee_id=employee.id,
                movement_type="انتداب",
                destination_branch_id=new_destination.id,
                from_date=date(2026, 2, 1),
                to_date=date(2026, 2, 5),
                status="مسجلة",
                is_active=True,
                created_by=actor.id,
                assignment_state="مغلق",
                mission_state="مغلقة",
            ),
        ])
        db.session.flush()

        summaries = latest_assignment_summaries({employee.id})
        summary = summaries[employee.id]
        assert summary["destination"] == "وجهة أحدث"
        assert summary["governorate"] == "محافظة اختبار الوجهة"
        assert summary["from_date"] == "01/02/2026"
        assert summary["to_date"] == "05/02/2026"
        assert summary["state"] == "مغلقة"
        assert "محافظة اختبار الوجهة" in summary["text"]

        db.session.rollback()
