from django.core.management.base import BaseCommand
from django.db import transaction

from apps.applications.models import Question, QuestionOption

SEED = [
    {
        "order": 1, "code": "name", "type": Question.TEXT,
        "text": "What is your full name?",
    },
    {
        "order": 2, "code": "country", "type": Question.CHOICE,
        "text": "Which country are you based in?",
        "has_other": True,
        "options": [
            ("kz", "Kazakhstan"), ("kg", "Kyrgyzstan"), ("uz", "Uzbekistan"),
            ("tj", "Tajikistan"), ("tm", "Turkmenistan"),
        ],
    },
    {
        "order": 3, "code": "city", "type": Question.TEXT,
        "text": "Which city are you in?",
    },
    {
        "order": 4, "code": "institution", "type": Question.TEXT,
        "text": "What is your current institution or organization?\n"
                "(e.g. Nazarbayev University, University of Helsinki, company, school)",
    },
    {
        "order": 5, "code": "level", "type": Question.CHOICE,
        "text": "What is your current level?",
        "has_other": True,
        "options": [
            ("bachelor", "Bachelor student"),
            ("master", "Master student"),
            ("phd", "PhD student"),
            ("postdoc", "Postdoc / Researcher"),
            ("professor", "Professor"),
            ("industry", "Industry"),
            ("entrepreneur", "Entrepreneur / Startup"),
        ],
    },
    {
        "order": 6, "code": "field", "type": Question.CHOICE,
        "text": "What is your main field?",
        "has_other": True,
        "options": [
            ("bio", "Biology & Biomedical Sciences"),
            ("ai", "AI / ML / Data Science"),
            ("physics", "Physics & Astronomy"),
            ("chem", "Chemistry & Materials Science"),
            ("eng", "Engineering"),
            ("math", "Mathematics & Theory"),
            ("interdisciplinary", "Interdisciplinary"),
        ],
    },
    {
        "order": 7, "code": "focus", "type": Question.CHOICE,
        "text": "What are you most interested in within CAST?",
        "has_other": True,
        "options": [
            ("networking", "Networking"),
            ("collab", "Research collaborations"),
            ("opportunities", "Opportunities (PhD / internships)"),
            ("learning", "Learning / discussions"),
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the initial CAST application questions (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        for item in SEED:
            q, _ = Question.objects.update_or_create(
                code=item["code"],
                defaults={
                    "order": item["order"],
                    "text": item["text"],
                    "question_type": item["type"],
                    "has_other": item.get("has_other", False),
                    "is_active": True,
                },
            )
            q.options.all().delete()
            for i, (value, label) in enumerate(item.get("options", [])):
                QuestionOption.objects.create(question=q, order=i, value=value, label=label)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(SEED)} questions."))
