import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'maincore.settings')
django.setup()

from jobs.models import Skill

def seed_skills():
    it_skills = [
        "Python", "JavaScript", "TypeScript", "React", "Next.js", "Node.js", "Django", "FastAPI",
        "PostgreSQL", "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
        "Terraform", "GraphQL", "REST API", "Machine Learning", "Deep Learning", "NLP",
        "Computer Vision", "Data Science", "Pandas", "NumPy", "Scikit-learn", "PyTorch",
        "TensorFlow", "DevOps", "CI/CD", "Git", "GitHub", "Bitbucket", "HTML5", "CSS3",
        "Tailwind CSS", "SASS", "Redux", "Zustand", "Prisma", "Drizzle", "SQL", "NoSQL",
        "Java", "Spring Boot", "C++", "C#", ".NET", "Go", "Rust", "Ruby", "Rails",
        "Swift", "Kotlin", "Flutter", "React Native", "Unity", "Unreal Engine",
        "Cybersecurity", "Ethical Hacking", "Blockchain", "Solidity", "Web3", "Go Lang",
        "Vue.js", "Angular", "Express.js", "MySQL", "Elasticsearch", "Jenkins", "Ansible"
    ]

    non_it_skills = [
        "Project Management", "Agile", "Scrum", "Product Management", "UI/UX Design", "Figma",
        "Adobe XD", "Photoshop", "Illustrator", "Digital Marketing", "SEO", "SEM",
        "Content Writing", "Copywriting", "Social Media Management", "Data Entry",
        "Customer Support", "Sales", "Business Development", "Financial Analysis",
        "Accounting", "Human Resources", "Recruitment", "Public Speaking", "Leadership",
        "Problem Solving", "Communication Skills", "Time Management", "Creative Thinking",
        "Emotional Intelligence", "Microsoft Excel", "Microsoft Word", "PowerPoint",
        "Google Analytics", "Market Research", "Branding", "Video Editing", "Premiere Pro",
        "After Effects", "Sound Engineering", "Event Planning", "Logistics",
        "Supply Chain Management", "Operations Management", "Business Strategy",
        "Soft Skills", "Teamwork", "Public Relations", "Salesforce", "Customer Success"
    ]

    # Insert IT Skills
    for name in it_skills:
        Skill.objects.get_or_create(name=name, category='IT')
    
    # Insert Non-IT Skills
    for name in non_it_skills:
        Skill.objects.get_or_create(name=name, category='NON_IT')

    print(f"Successfully seeded {len(it_skills)} IT skills and {len(non_it_skills)} Non-IT skills.")

if __name__ == "__main__":
    seed_skills()
