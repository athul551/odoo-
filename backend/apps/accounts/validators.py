from django.core.exceptions import ValidationError


class BrightloopPasswordPolicyValidator:
    """
    Spec: password must be more than eight characters (>= 9), and contain at
    least one uppercase letter, one lowercase letter and one special character.
    Length itself is delegated to MinimumLengthValidator (min_length=9).
    """

    def validate(self, password, user=None):
        problems = []
        specials = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
        problems = []
        if not any(c.isupper() for c in password):
            problems.append("must contain an uppercase letter (A-Z)")
        if not any(c.islower() for c in password):
            problems.append("must contain a lowercase letter (a-z)")
        if not any(c in specials for c in password):
            problems.append("must contain a special character (!@#$%^&*, etc.)")
        if problems:
            raise ValidationError(
                "Password " + ", ".join(problems) + ".",
                code="password_policy",
            )

    def get_help_text(self):
        return (
            "Your password must contain at least one uppercase letter, "
            "one lowercase letter and one special character."
        )
