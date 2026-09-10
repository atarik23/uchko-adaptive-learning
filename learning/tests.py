from django.test import SimpleTestCase

from .content_sanitizer import sanitize_learning_html


class LearningContentSanitizerTests(SimpleTestCase):
    def test_removes_active_and_dangerous_content(self):
        result = sanitize_learning_html(
            """
            <script>alert(1)</script>
            <p style="color:red; position:fixed">
                Safe
                <img
                    src="data:image/svg+xml,bad"
                    onerror="alert(2)"
                >
            </p>
            """
        )

        self.assertNotIn("<script", result)
        self.assertNotIn("alert(1)", result)
        self.assertNotIn("onerror", result)
        self.assertNotIn("position", result)
        self.assertNotIn("data:image", result)
        self.assertIn("color:red", result)
        self.assertIn("Safe", result)

    def test_preserves_required_mathml(self):
        result = sanitize_learning_html(
            """
            <math>
                <mfrac>
                    <mn>1</mn>
                    <mn>2</mn>
                </mfrac>
            </math>
            """
        )

        self.assertIn("<math>", result)
        self.assertIn("<mfrac>", result)
        self.assertIn("<mn>1</mn>", result)
        self.assertIn("<mn>2</mn>", result)

    def test_allows_known_https_image_host(self):
        result = sanitize_learning_html(
            """
            <img
                src="https://resources.assistments.org/example.png"
                alt="Example"
            >
            """
        )

        self.assertIn(
            'src="https://resources.assistments.org/example.png"',
            result,
        )
        self.assertIn('alt="Example"', result)

    def test_removes_unknown_image_host(self):
        result = sanitize_learning_html(
            '<img src="https://malicious.example/image.png">'
        )

        self.assertNotIn("malicious.example", result)

    def test_allows_relative_image_path(self):
        result = sanitize_learning_html(
            '<img src="/resources/example.png">'
        )

        self.assertIn(
            'src="/resources/example.png"',
            result,
        )

    def test_rewrites_protocol_relative_image_url(self):
        result = sanitize_learning_html(
            """
            <img
                src="//resources.assistments.org/fetch/C/example.jpeg"
            >
            """
        )

        self.assertIn(
            (
                'src="https://resources.assistments.org/'
                'fetch/C/example.jpeg"'
            ),
            result,
        )


    def test_rewrites_legacy_assistments_image_path(self):
        result = sanitize_learning_html(
            """
            <img
                src="/images/assistments/189043.jpg"
            >
            """
        )

        self.assertIn(
            (
                'src="https://app.assistments.org/'
                'images/assistments/189043.jpg"'
            ),
            result,
    )