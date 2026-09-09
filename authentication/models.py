from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Admin'
    MANAGER = 'MANAGER', 'Manager'
    DRIVER = 'DRIVER', 'Driver'
    STUDENT = 'STUDENT', 'Student'

class User(AbstractUser):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STUDENT
    )

    
    birth_date = models.DateField(null=True, blank=True)
    

    # city = models.ForeignKey('management.City', on_delete=models.SET_NULL, null=True, blank=True)
    
    profile_picture = models.ImageField(upload_to='avatars/', null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    @property
    def avatar_url(self):
        if self.profile_picture and hasattr(self.profile_picture, 'url'):
            return self.profile_picture.url
        return '/static/images/default-avatar.png'

class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile')
    # institution = models.ForeignKey('management.EducationalInstitution', on_delete=models.PROTECT)
    course = models.CharField(max_length=100)
    period = models.PositiveIntegerField()

    def __str__(self):
        return f"Estudante: {self.user.full_name}"