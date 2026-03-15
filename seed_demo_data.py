import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'horilla.settings')
django.setup()

from django.core.management import call_command
from django.apps import apps
from django.contrib.auth.models import User

def seed():
    # Delete existing data to avoid PK conflicts for demo load
    print("Cleaning existing users and employees...")
    try:
        User.objects.all().delete()
    except Exception as e:
        print(f"Warning during cleanup: {e}")
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOAD_DATA_DIR = os.path.join(BASE_DIR, 'load_data')
    
    data_files = [
        "user_data.json",
        "employee_info_data.json",
        "base_data.json",
        "work_info_data.json",
        "tags.json",
        "faq_category.json",
        "faq.json",
        "mail_templates.json",
        "mail_automations.json",
    ]
    
    optional_apps = [
        ("attendance", "attendance_data.json"),
        ("leave", "leave_data.json"),
        ("asset", "asset_data.json"),
        ("recruitment", "recruitment_data.json"),
        ("onboarding", "onboarding_data.json"),
        ("offboarding", "offboarding_data.json"),
        ("pms", "pms_data.json"),
        ("payroll", "payroll_data.json"),
        ("payroll", "payroll_loanaccount_data.json"),
        ("project", "project_data.json"),
    ]
    
    data_files += [file for app, file in optional_apps if apps.is_installed(app)]
    
    for file in data_files:
        file_path = os.path.join(LOAD_DATA_DIR, file)
        if os.path.exists(file_path):
            print(f"Loading {file}...")
            try:
                call_command('loaddata', file_path)
            except Exception as e:
                print(f"Error loading {file}: {e}")
        else:
            print(f"File {file} not found at {file_path}, skipping.")

    # Re-create the user's preferred admin if not already present or needs update
    print("Ensuring user's admin account exists...")
    admin_email = 'admin@ensuredit.com'
    admin_pass = 'admin123456'
    
    user = User.objects.filter(email=admin_email).first()
    if not user:
        if not User.objects.filter(username=admin_email).exists():
            User.objects.create_superuser(username=admin_email, email=admin_email, password=admin_pass)
            print(f"Created superuser {admin_email}")
        else:
            user = User.objects.get(username=admin_email)
            user.email = admin_email
            user.set_password(admin_pass)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            print(f"Updated existing user with username {admin_email}")
    else:
        user.set_password(admin_pass)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        print(f"Updated existing user {admin_email} with password and superuser status.")

if __name__ == "__main__":
    seed()
