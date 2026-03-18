# tests/test_student_group.py
def test_student_has_group_code_attribute(db):
    from models import Student, Semester
    with db.session.begin_nested():
        sem = Semester(code="TEST", name="Test")
        db.session.add(sem)
    db.session.flush()
    s = Student(semester_id=sem.id, matrikel="123", last_name="Test",
                first_name="A", running_number=1, group_code="A")
    db.session.add(s)
    db.session.flush()
    assert s.group_code == "A"

def test_student_group_code_nullable(db):
    from models import Student, Semester
    with db.session.begin_nested():
        sem = Semester(code="TEST2", name="Test2")
        db.session.add(sem)
    db.session.flush()
    s = Student(semester_id=sem.id, matrikel="456", last_name="Test",
                first_name="B", running_number=2)
    db.session.add(s)
    db.session.flush()
    assert s.group_code is None

def test_student_group_code_must_be_valid(db):
    from models import Student, Semester
    import pytest
    with db.session.begin_nested():
        sem = Semester(code="TEST3", name="Test3")
        db.session.add(sem)
    db.session.flush()
    s = Student(semester_id=sem.id, matrikel="789", last_name="Test",
                first_name="C", running_number=3, group_code="X")
    db.session.add(s)
    with pytest.raises(Exception):
        db.session.flush()
