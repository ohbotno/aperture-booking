# Generated by Django 5.2.3 on 2025-07-20 22:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0009_add_requires_risk_assessment_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="userriskassessment",
            name="assessment_file",
            field=models.FileField(
                blank=True,
                help_text="Supporting documents (Excel, PDF, Word, etc.)",
                null=True,
                upload_to="risk_assessments/",
            ),
        ),
    ]
