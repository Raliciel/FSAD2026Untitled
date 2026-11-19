from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator

MAX_IMAGE_BYTES = 2 * 1024 * 1024
PASSWORD_SPECIAL_CHARACTERS = '!@#$%^&*()_+'


def validate_image_size(f):
    if f.size > MAX_IMAGE_BYTES:
        raise ValidationError("Image must be 2 MB or smaller.")


IMAGE_VALIDATORS = [
    FileExtensionValidator(["jpg", "jpeg", "png", "webp"]),
    validate_image_size,
]

# UC01-01: usernames may not contain !@#$%^&*()_+ . Allow-list instead of block-list (4.3.7).
username_validator = RegexValidator(
    r"^[A-Za-z0-9.-]+\Z",
    "Username may contain only letters, numbers, dots and hyphens.",
)


class PasswordComplexityValidator:
    """UC01-01: at least one upper case, one lower case and one special character."""

    def validate(self, password, user=None):
        errors = []
        if not any(c.isupper() for c in password):
            errors.append("an upper case letter")
        if not any(c.islower() for c in password):
            errors.append("a lower case letter")
        if not any(c in PASSWORD_SPECIAL_CHARACTERS for c in password):
            errors.append(f"a special character ({PASSWORD_SPECIAL_CHARACTERS})")
        if errors:
            raise ValidationError(
                "Password must contain " + ", ".join(errors) + ".",
                code="password_too_simple",
            )

    def get_help_text(self):
        return (
            "Your password must contain an upper case letter, a lower case letter and "
            f"a special character ({PASSWORD_SPECIAL_CHARACTERS})."
        )
