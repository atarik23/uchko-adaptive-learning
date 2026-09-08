from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from courses.models import Course, Enrollment


class CourseAuthorizationTests(TestCase):
    def setUp(self):
        self.professor_a = User.objects.create_user(
            username="professor_a",
            password="TestPassword123!",
            role=User.Role.PROFESSOR,
        )

        self.professor_b = User.objects.create_user(
            username="professor_b",
            password="TestPassword123!",
            role=User.Role.PROFESSOR,
        )

        self.student_a = User.objects.create_user(
            username="student_a",
            password="TestPassword123!",
            role=User.Role.STUDENT,
        )

        self.student_b = User.objects.create_user(
            username="student_b",
            password="TestPassword123!",
            role=User.Role.STUDENT,
        )

        self.course_a = Course.objects.create(
            name="Course A",
            code="COURSE-A",
            professor=self.professor_a,
        )

        self.course_b = Course.objects.create(
            name="Course B",
            code="COURSE-B",
            professor=self.professor_b,
        )

        self.enrollment_a = Enrollment.objects.create(
            course=self.course_a,
            student=self.student_a,
        )

        self.enrollment_b = Enrollment.objects.create(
            course=self.course_b,
            student=self.student_b,
        )

    def test_anonymous_user_cannot_open_student_dashboard(self):
        response = self.client.get(
            reverse("courses:student_dashboard")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:login"),
            response.url,
        )

    def test_professor_cannot_open_student_dashboard(self):
        self.client.force_login(self.professor_a)

        response = self.client.get(
            reverse("courses:student_dashboard")
        )

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_open_professor_dashboard(self):
        self.client.force_login(self.student_a)

        response = self.client.get(
            reverse("courses:professor_dashboard")
        )

        self.assertEqual(response.status_code, 403)

    def test_professor_can_open_own_student_details(self):
        self.client.force_login(self.professor_a)

        response = self.client.get(
            reverse(
                "courses:professor_student_detail",
                args=[self.enrollment_a.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student_a.username)
        self.assertContains(response, self.course_a.name)

    def test_professor_cannot_open_another_professors_student(self):
        self.client.force_login(self.professor_a)

        response = self.client.get(
            reverse(
                "courses:professor_student_detail",
                args=[self.enrollment_b.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_student_dashboard_contains_only_own_course(self):
        self.client.force_login(self.student_a)

        response = self.client.get(
            reverse("courses:student_dashboard")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_a.name)
        self.assertNotContains(response, self.course_b.name)
        self.assertNotContains(response, self.student_b.username)