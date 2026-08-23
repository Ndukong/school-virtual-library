"""Create or reuse a school and attach a new administrator user to it."""

import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from schools.models import School


class Command(BaseCommand):
    help = "Create (or reuse) a school and add a new administrator user for it."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School name; created if it does not exist.")
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument(
            "--password",
            default=None,
            help="Password. Omit to be prompted securely.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User '{username}' already exists.")

        password = options["password"] or getpass.getpass("Password: ")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        school, school_created = School.objects.get_or_create(name=options["school"])
        user = User.objects.create_user(
            username=username,
            email=options["email"],
            password=password,
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=User.Role.ADMIN,
            school=school,
            is_staff=True,
        )

        verb = "Created" if school_created else "Reused"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} school '{school.name}'; created administrator '{user.username}'."
            )
        )