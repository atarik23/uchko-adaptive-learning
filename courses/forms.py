from django import forms


class EnrollmentCodeForm(forms.Form):
    enrollment_code = forms.CharField(
        max_length=64,
        label="Enrollment code",
        help_text="Enter the code provided by your professor.",
    )

    def clean_enrollment_code(self):
        return self.cleaned_data["enrollment_code"].strip()