# Generated by Django 5.2.3 on 2025-06-17 20:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0025_aboutpage"),
    ]

    operations = [
        migrations.AddField(
            model_name="aboutpage",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="Optional image to display alongside the content",
                null=True,
                upload_to="about_page/",
            ),
        ),
    ]
