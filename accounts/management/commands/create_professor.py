from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a professor account for Uchko."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Professor username. If omitted, you will be prompted.",
        )
        parser.add_argument(
            "--email",
            help="Professor email address. If omitted, you will be prompted.",
        )
        parser.add_argument(
            "--first-name",
            dest="first_name",
            help="Professor first name. If omitted, you will be prompted.",
        )
        parser.add_argument(
            "--last-name",
            dest="last_name",
            help="Professor last name. If omitted, you will be prompted.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        username = (options.get("username") or input("Username: ")).strip()
        first_name = (options.get("first_name") or input("First name: ")).strip()
        last_name = (options.get("last_name") or input("Last name: ")).strip()
        email = (options.get("email") or input("Email: ")).strip().lower()

        if not username:
            raise CommandError("Username cannot be empty.")

        if not email:
            raise CommandError("Email cannot be empty.")

        if User.objects.filter(username__iexact=username).exists():
            raise CommandError("A user with this username already exists.")

        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("A user with this email address already exists.")

        password = self._prompt_for_password()

        professor = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=User.Role.PROFESSOR,
        )
        professor.set_password(password)
        professor.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Professor "{professor.username}" was created successfully.'
            )
        )

    def _prompt_for_password(self):
        from getpass import getpass

        password = getpass("Password: ")
        confirmation = getpass("Password (again): ")

        if password != confirmation:
            raise CommandError("Passwords do not match.")

        if not password:
            raise CommandError("Password cannot be empty.")

        return password