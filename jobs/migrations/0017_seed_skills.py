# Generated data migration to seed skills in the market

from django.db import migrations

def seed_skills(apps, schema_editor):
    Skill = apps.get_model('jobs', 'Skill')
    skills_data = [
        # IT Skills
        {"name": "Python", "category": "IT"},
        {"name": "JavaScript", "category": "IT"},
        {"name": "TypeScript", "category": "IT"},
        {"name": "React", "category": "IT"},
        {"name": "Next.js", "category": "IT"},
        {"name": "Django", "category": "IT"},
        {"name": "Node.js", "category": "IT"},
        {"name": "Vue.js", "category": "IT"},
        {"name": "Angular", "category": "IT"},
        {"name": "HTML5", "category": "IT"},
        {"name": "CSS3", "category": "IT"},
        {"name": "Tailwind CSS", "category": "IT"},
        {"name": "PyTorch", "category": "IT"},
        {"name": "TensorFlow", "category": "IT"},
        {"name": "Machine Learning", "category": "IT"},
        {"name": "Deep Learning", "category": "IT"},
        {"name": "Natural Language Processing (NLP)", "category": "IT"},
        {"name": "LLMs", "category": "IT"},
        {"name": "AI Agents", "category": "IT"},
        {"name": "Prompt Engineering", "category": "IT"},
        {"name": "Java", "category": "IT"},
        {"name": "C++", "category": "IT"},
        {"name": "C#", "category": "IT"},
        {"name": "Go", "category": "IT"},
        {"name": "Rust", "category": "IT"},
        {"name": "Ruby on Rails", "category": "IT"},
        {"name": "PHP", "category": "IT"},
        {"name": "Amazon Web Services (AWS)", "category": "IT"},
        {"name": "Microsoft Azure", "category": "IT"},
        {"name": "Google Cloud Platform (GCP)", "category": "IT"},
        {"name": "Docker", "category": "IT"},
        {"name": "Kubernetes", "category": "IT"},
        {"name": "CI/CD", "category": "IT"},
        {"name": "Terraform", "category": "IT"},
        {"name": "SQL", "category": "IT"},
        {"name": "PostgreSQL", "category": "IT"},
        {"name": "MongoDB", "category": "IT"},
        {"name": "Redis", "category": "IT"},
        {"name": "GraphQL", "category": "IT"},
        {"name": "MySQL", "category": "IT"},
        {"name": "Solidity", "category": "IT"},
        {"name": "Web3", "category": "IT"},
        {"name": "Figma", "category": "IT"},
        {"name": "UI/UX Design", "category": "IT"},
        # Non-IT Skills
        {"name": "Product Management", "category": "NON_IT"},
        {"name": "Agile/Scrum", "category": "NON_IT"},
        {"name": "Business Development", "category": "NON_IT"},
        {"name": "Digital Marketing", "category": "NON_IT"},
        {"name": "SEO", "category": "NON_IT"},
        {"name": "Financial Analysis", "category": "NON_IT"},
        {"name": "Sales", "category": "NON_IT"},
        {"name": "Recruiting", "category": "NON_IT"},
        {"name": "Content Writing", "category": "NON_IT"},
        {"name": "Project Management", "category": "NON_IT"},
        {"name": "Customer Success", "category": "NON_IT"},
        {"name": "Growth Hacking", "category": "NON_IT"},
        {"name": "Public Relations", "category": "NON_IT"},
        {"name": "Operations Management", "category": "NON_IT"},
    ]
    for skill in skills_data:
        Skill.objects.get_or_create(name=skill["name"], defaults={"category": skill["category"]})

def remove_skills(apps, schema_editor):
    Skill = apps.get_model('jobs', 'Skill')
    Skill.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0016_savedjob'),
    ]

    operations = [
        migrations.RunPython(seed_skills, remove_skills),
    ]
