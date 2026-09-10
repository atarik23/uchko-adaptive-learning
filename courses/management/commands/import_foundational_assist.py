import ast
import json
from pathlib import Path

import pandas as pd

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from courses.models import (
    Course,
    KnowledgeComponent,
    LearningItem,
)


DATASET_NAME = "ASSISTments/FoundationalASSIST"
DATASET_LICENSE = (
    "CC-BY-NC-4.0 dataset; source-item attribution may vary"
)


def parse_list_value(value, delimiter=None):
    if value is None:
        return []

    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass

    if isinstance(value, list):
        parsed_values = value
    elif isinstance(value, tuple):
        parsed_values = list(value)
    elif isinstance(value, set):
        parsed_values = sorted(value)
    elif isinstance(value, dict):
        parsed_values = [value]
    else:
        text = str(value).strip()

        if not text:
            return []

        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = text

        if isinstance(parsed, list):
            parsed_values = parsed
        elif isinstance(parsed, tuple):
            parsed_values = list(parsed)
        elif isinstance(parsed, set):
            parsed_values = sorted(parsed)
        else:
            parsed_values = [parsed]

    normalized_values = []

    for parsed_value in parsed_values:
        if (
            delimiter
            and isinstance(parsed_value, str)
            and delimiter in parsed_value
        ):
            normalized_values.extend(
                part.strip()
                for part in parsed_value.split(delimiter)
                if part.strip()
            )
        else:
            normalized_values.append(parsed_value)

    return normalized_values


def string_value(value, default=""):
    if pd.isna(value):
        return default

    text = str(value).strip()
    return text or default


class Command(BaseCommand):
    help = (
        "Import FoundationalASSIST problems and skills "
        "without importing protected student interactions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--course-code",
            required=True,
            help="Code of an existing Uchko course.",
        )

        parser.add_argument(
            "--problems",
            required=True,
            help="Absolute or relative path to Problems.csv.",
        )

        parser.add_argument(
            "--skills",
            required=True,
            help="Absolute or relative path to Skills.csv.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        course_code = options["course_code"]
        problems_path = Path(
            options["problems"]
        ).expanduser().resolve()
        skills_path = Path(
            options["skills"]
        ).expanduser().resolve()

        try:
            course = Course.objects.get(
                code=course_code
            )
        except Course.DoesNotExist as error:
            raise CommandError(
                f"Course '{course_code}' does not exist."
            ) from error

        if not problems_path.is_file():
            raise CommandError(
                f"Problems file not found: {problems_path}"
            )

        if not skills_path.is_file():
            raise CommandError(
                f"Skills file not found: {skills_path}"
            )

        self.stdout.write("Loading problem metadata...")

        problems = pd.read_csv(problems_path)

        required_problem_columns = {
            "Problem Set Id",
            "Problem Part",
            "Problem Type",
            "Answer Types",
            "Problem Body",
            "Fill-in Options",
            "Fill-in Answers",
            "Multiple Choice Options",
            "Multiple Choice Answers",
            "problem_id",
        }

        missing_problem_columns = (
            required_problem_columns
            - set(problems.columns)
        )

        if missing_problem_columns:
            raise CommandError(
                "Problems.csv is missing columns: "
                + ", ".join(
                    sorted(missing_problem_columns)
                )
            )

        # Trening pipeline je potpuno isključio svaki
        # problem_id koji se pojavljivao više puta.
        duplicate_problem_ids = set(
            problems.loc[
                problems.duplicated(
                    "problem_id",
                    keep=False,
                ),
                "problem_id",
            ]
        )

        problems = problems[
            ~problems["problem_id"].isin(
                duplicate_problem_ids
            )
        ].copy()

        self.stdout.write("Loading skill metadata...")

        skills = pd.read_csv(skills_path)

        required_skill_columns = {
            "problem_id",
            "skill_id",
            "node_code",
            "node_name",
        }

        missing_skill_columns = (
            required_skill_columns
            - set(skills.columns)
        )

        if missing_skill_columns:
            raise CommandError(
                "Skills.csv is missing columns: "
                + ", ".join(
                    sorted(missing_skill_columns)
                )
            )

        valid_problem_ids = set(
            problems["problem_id"]
        )

        skills = skills[
            skills["problem_id"].isin(
                valid_problem_ids
            )
        ].copy()

        skills["node_code"] = (
            skills["node_code"]
            .fillna("unknown")
            .astype(str)
            .str.strip()
        )

        skills["node_name"] = (
            skills["node_name"]
            .fillna("Unknown skill")
            .astype(str)
            .str.strip()
        )

        skills = skills.sort_values(
            ["problem_id", "node_code", "skill_id"]
        )

        self.stdout.write(
            "Creating knowledge components..."
        )

        components_by_code = {}

        component_rows = (
            skills[
                ["node_code", "node_name"]
            ]
            .drop_duplicates(
                subset=["node_code"],
                keep="first",
            )
            .sort_values("node_code")
        )

        for _, row in component_rows.iterrows():
            node_code = string_value(
                row["node_code"],
                "unknown",
            )

            component, _ = (
                KnowledgeComponent.objects.update_or_create(
                    course=course,
                    external_id=node_code,
                    defaults={
                        "name": string_value(
                            row["node_name"],
                            "Unknown skill",
                        ),
                        "description": "",
                        "metadata": {
                            "source_dataset": DATASET_NAME,
                        },
                    },
                )
            )

            components_by_code[node_code] = component

        skill_groups = {
            problem_id: group
            for problem_id, group in skills.groupby(
                "problem_id",
                sort=False,
            )
        }

        created_count = 0
        updated_count = 0
        skipped_without_skill = 0

        self.stdout.write("Creating learning items...")

        for _, row in problems.iterrows():
            problem_id = row["problem_id"]

            skill_group = skill_groups.get(problem_id)

            if skill_group is None or skill_group.empty:
                skipped_without_skill += 1
                continue

            node_codes = list(
                dict.fromkeys(
                    skill_group[
                        "node_code"
                    ].astype(str)
                )
            )

            # Isti izbor kao u prepare_data.py:
            # sortiranje po problem_id, node_code i skill_id,
            # a zatim uzimanje prvog node_code.
            primary_code = node_codes[0]
            primary_component = (
                components_by_code[primary_code]
            )

            problem_part = pd.to_numeric(
                row["Problem Part"],
                errors="coerce",
            )

            if pd.isna(problem_part):
                problem_part = None
            else:
                problem_part = int(problem_part)

            item, created = (
                LearningItem.objects.update_or_create(
                    course=course,
                    external_id=str(problem_id),
                    defaults={
                        "problem_set_id": string_value(
                            row["Problem Set Id"],
                            "unknown",
                        ),
                        "problem_part": problem_part,
                        "problem_type": string_value(
                            row["Problem Type"],
                            "unknown",
                        ),
                        "answer_type": string_value(
                            row["Answer Types"],
                            "unknown",
                        ),
                        "body": string_value(
                            row["Problem Body"]
                        ),
                        "fill_in_options": parse_list_value(
                            row["Fill-in Options"],
                            delimiter="</p>,",
                        ),
                        "fill_in_answers": parse_list_value(
                            row["Fill-in Answers"],
                        ),
                        "multiple_choice_options": (
                            parse_list_value(
                                row[
                                    "Multiple Choice Options"
                                ],
                                delimiter="||",
                            )
                        ),
                        "multiple_choice_answers": (
                            parse_list_value(
                                row[
                                    "Multiple Choice Answers"
                                ],
                                delimiter="||",
                            )
                        ),
                        "primary_knowledge_component": (
                            primary_component
                        ),
                        "skill_count": max(
                            int(
                                skill_group[
                                    "skill_id"
                                ].nunique()
                            ),
                            1,
                        ),
                        "source_dataset": DATASET_NAME,
                        "source_license": DATASET_LICENSE,
                        "is_active": True,
                        "metadata": {
                            "imported_by": (
                                "import_foundational_assist"
                            ),
                        },
                    },
                )
            )

            item.knowledge_components.set(
                [
                    components_by_code[code]
                    for code in node_codes
                ]
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "FoundationalASSIST import completed."
            )
        )
        self.stdout.write(
            f"Course: {course.code}"
        )
        self.stdout.write(
            f"Knowledge components: "
            f"{len(components_by_code)}"
        )
        self.stdout.write(
            f"Learning items created: {created_count}"
        )
        self.stdout.write(
            f"Learning items updated: {updated_count}"
        )
        self.stdout.write(
            f"Problems skipped without skills: "
            f"{skipped_without_skill}"
        )
        self.stdout.write(
            f"Duplicate problem IDs excluded: "
            f"{len(duplicate_problem_ids)}"
        )