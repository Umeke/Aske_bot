from django.conf import settings
from django.db import models


class Question(models.Model):
    TEXT = "text"
    CHOICE = "choice"
    TYPE_CHOICES = [(TEXT, "Free text"), (CHOICE, "Buttons")]

    order = models.PositiveIntegerField(unique=True)
    code = models.SlugField(unique=True)
    text = models.TextField()
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TEXT)
    is_active = models.BooleanField(default=True)
    has_other = models.BooleanField(default=False, help_text="Add 'Other' button with free-text follow-up")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.order}. {self.code}"


class QuestionOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    order = models.PositiveIntegerField(default=0)
    value = models.SlugField()
    label = models.CharField(max_length=100)

    class Meta:
        ordering = ["order"]
        unique_together = [("question", "value")]

    def __str__(self):
        return self.label


class Application(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [(PENDING, "Pending"), (APPROVED, "Approved"), (REJECTED, "Rejected")]

    telegram_id = models.BigIntegerField(unique=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    invite_link = models.URLField(blank=True)
    joined_group = models.BooleanField(default=False)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"#{self.pk} @{self.telegram_username or self.telegram_id} [{self.status}]"

    @property
    def display_name(self) -> str:
        answer = self.answers.filter(question__code="name").first()
        return answer.value if answer else f"@{self.telegram_username or self.telegram_id}"


class Answer(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    value = models.TextField()

    class Meta:
        unique_together = [("application", "question")]

    def __str__(self):
        return f"{self.question.code}: {self.value[:40]}"
