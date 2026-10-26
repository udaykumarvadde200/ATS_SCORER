"""Generate the synthetic test resumes used by run_evaluation.py.

All people, emails and phone numbers are fictional (example.com addresses).
Tiers are written to follow ordinary resume advice, independent of the app:
  weak       - thin content, vague duties, long unbacked skills list or none
  average    - all sections, but few strong verbs and almost no numbers
  good       - verb-led bullets, some numbers, most skills used in projects
  excellent  - every bullet verb-led, numbers in most bullets, every skill
               backed by a project or job, complete contact details
"""

import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resumes")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], fontSize=17, leading=21, spaceAfter=2)
CONTACT = ParagraphStyle("C", parent=styles["Normal"], fontSize=9, alignment=1, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("B", parent=styles["Normal"], fontSize=9.5, leading=12.5)
BUL = ParagraphStyle("U", parent=BODY, leftIndent=12, bulletIndent=2)
SUB = ParagraphStyle("S", parent=BODY, fontName="Helvetica-Bold", spaceBefore=3)


def build(path, d):
    story = [Paragraph(d["name"], H1), Paragraph(d["contact"], CONTACT)]
    if d.get("summary"):
        story += [Paragraph(d.get("summary_title", "SUMMARY"), H2), Paragraph(d["summary"], BODY)]
    if d.get("skills"):
        story.append(Paragraph("TECHNICAL SKILLS", H2))
        for line in d["skills"]:
            story.append(Paragraph(line, BODY))
    if d.get("experience"):
        story.append(Paragraph("EXPERIENCE", H2))
        for title, dates, bullets in d["experience"]:
            story.append(Paragraph(f"{title} | {dates}", SUB))
            for b in bullets:
                story.append(Paragraph(b, BUL, bulletText="\u2022"))
    if d.get("projects"):
        story.append(Paragraph("PROJECTS", H2))
        for title, bullets in d["projects"]:
            story.append(Paragraph(title, SUB))
            for b in bullets:
                story.append(Paragraph(b, BUL, bulletText="\u2022"))
    if d.get("education"):
        story.append(Paragraph("EDUCATION", H2))
        for line in d["education"]:
            story.append(Paragraph(line, BODY))
    if d.get("extra"):
        for title, lines in d["extra"]:
            story.append(Paragraph(title, H2))
            for line in lines:
                story.append(Paragraph(line, BUL, bulletText="\u2022"))
    SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm).build(story)


def contact(n, full=True):
    base = f"candidate{n:02d}@example.com"
    if not full:
        return base
    return f"{base} | +91 90000 000{n:02d} | Hyderabad, India | github.com/sample-candidate-{n:02d} | linkedin.com/in/sample-candidate-{n:02d}"


R = {}

# ----------------------------------------------------------------- WEAK
R["weak/01"] = dict(
    name="Sample Candidate 01", contact=contact(1, False),
    summary_title="OBJECTIVE", summary="Looking for a job where I can learn and grow.",
    projects=[("Student Result Portal", ["Website for student results", "Made using HTML and some database"]),
              ("Library App", ["Library management", "Responsible for the front page"])],
    education=["B.Tech Computer Science, Sample Institute of Technology"],
)
R["weak/02"] = dict(
    name="Sample Candidate 02", contact="candidate02@example.com | +91 90000 00002",
    skills=["Python, Java, C, C++, SQL, HTML, CSS, JavaScript, React, Node.js, Machine Learning, Deep Learning, NLP, "
            "Computer Vision, TensorFlow, PyTorch, Docker, Kubernetes, AWS, Git, Linux, MongoDB, Tableau, Excel"],
    projects=[("Chat Application", ["Responsible for making the website", "Group project in third year"]),
              ("Weather Page", ["Weather page with api"])],
    education=["B.Tech Information Technology, Sample College of Engineering"],
)
R["weak/03"] = dict(
    name="Sample Candidate 03", contact="candidate03@example.com",
    skills=["Hardworking, team player, quick learner, communication, leadership, problem solving, Python, Excel, Word"],
    experience=[("Intern, Sample Analytics Pvt Ltd", "2024", ["Worked on data", "Helped the team with tasks", "Duties as assigned by manager"])],
    education=["B.Sc Statistics, Sample University"],
)

# -------------------------------------------------------------- AVERAGE
R["average/01"] = dict(
    name="Sample Candidate 04", contact=contact(4),
    summary="Computer science student interested in machine learning and data analysis. Looking for an internship.",
    skills=["Languages: Python, SQL, Java", "Libraries: NumPy, Pandas, Scikit-learn, Matplotlib", "Tools: Git, Jupyter, VS Code",
            "Concepts: Machine Learning, Data Cleaning, Regression"],
    projects=[("House Price Prediction", ["Used the Ames housing dataset to predict prices with linear regression",
                                          "Data cleaning and feature engineering was done using Pandas",
                                          "Results were compared across models"]),
              ("Movie Recommender", ["Recommendation system using cosine similarity", "Built a simple interface in Streamlit"])],
    experience=[("Data Intern, Sample Analytics Pvt Ltd", "Jun 2024 - Aug 2024",
                 ["Assisted with cleaning sales data", "Prepared weekly reports", "Attended team meetings"])],
    education=["B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026"],
)
R["average/02"] = dict(
    name="Sample Candidate 05", contact=contact(5),
    summary="Final year student with experience in web development and a keen interest in building user-friendly applications.",
    skills=["Languages: JavaScript, Python, HTML, CSS", "Frameworks: React, Node.js, Express", "Databases: MongoDB, MySQL",
            "Tools: Git, Postman, Figma"],
    projects=[("Expense Tracker", ["Web application where users can add and view expenses", "Made with React and Node.js",
                                   "Uses MongoDB to store data"]),
              ("Portfolio Website", ["Personal portfolio built with HTML and CSS", "Hosted on GitHub Pages"])],
    experience=[("Web Development Intern, Sample Web Studio", "May 2024 - Jul 2024",
                 ["Worked on the company website", "Fixed some bugs", "Learned about agile process"])],
    education=["B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026"],
)
R["average/03"] = dict(
    name="Sample Candidate 06", contact=contact(6),
    summary="Data analytics student looking for opportunities to apply statistics and visualization skills.",
    skills=["Languages: Python, SQL, R", "Tools: Excel, Tableau, Power BI", "Libraries: Pandas, Matplotlib, Seaborn",
            "Concepts: Statistics, Dashboards, A/B Testing"],
    projects=[("Sales Dashboard", ["Dashboard for monthly sales using Tableau", "Data taken from a public retail dataset",
                                   "Charts for region and product"]),
              ("Customer Survey Analysis", ["Analysis of survey responses using Python", "Visualizations made with Seaborn"])],
    education=["B.Sc Statistics, Sample University, 2022 - 2025", "Diploma in Data Analytics, Sample Academy"],
)

# ----------------------------------------------------------------- GOOD
R["good/01"] = dict(
    name="Sample Candidate 07", contact=contact(7),
    summary="Computer science student specializing in machine learning, with hands-on experience building and evaluating models "
            "on tabular and text data.",
    skills=["Languages: Python, SQL", "ML: Scikit-learn, XGBoost, PyTorch", "Data: NumPy, Pandas, Matplotlib",
            "Tools: Git, Docker, Streamlit"],
    projects=[("Customer Churn Prediction", ["Built a churn classifier with Scikit-learn and XGBoost on a 7,000-customer dataset",
                                             "Engineered 12 features with Pandas and reached 84% accuracy",
                                             "Deployed the model as a Streamlit app packaged with Docker"]),
              ("Sentiment Analysis of Reviews", ["Trained a PyTorch LSTM on 25,000 movie reviews",
                                                 "Compared the model with a logistic regression baseline using Scikit-learn",
                                                 "Visualized results with Matplotlib"])],
    experience=[("Machine Learning Intern, Sample Analytics Pvt Ltd", "Jun 2024 - Aug 2024",
                 ["Cleaned and merged 3 sales datasets using SQL and Pandas",
                  "Built a forecasting prototype that the team used in weekly planning",
                  "Presented findings to a team of 8 analysts"])],
    education=["B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026"],
    extra=[("CERTIFICATIONS", ["Machine Learning Specialization, Sample Online Academy"])],
)
R["good/02"] = dict(
    name="Sample Candidate 08", contact=contact(8),
    summary="Full-stack developer in training who builds and deploys web applications with React, Node.js and MongoDB.",
    skills=["Languages: JavaScript, TypeScript, Python", "Frontend: React, HTML, CSS", "Backend: Node.js, Express, MongoDB",
            "Tools: Git, Docker, Postman"],
    projects=[("Expense Tracker", ["Developed a React and Node.js application used by 40 classmates to track monthly spending",
                                   "Designed 9 REST endpoints in Express with MongoDB storage",
                                   "Added authentication with JWT and tested the API with Postman"]),
              ("Task Board", ["Built a drag-and-drop task board in React with TypeScript",
                              "Containerized the app with Docker for one-command setup"])],
    experience=[("Web Development Intern, Sample Web Studio", "May 2024 - Jul 2024",
                 ["Fixed 15 front-end bugs in the company website",
                  "Implemented a responsive pricing page in React",
                  "Collaborated with 2 designers using Git branches and code reviews"])],
    education=["B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026"],
)
R["good/03"] = dict(
    name="Sample Candidate 09", contact=contact(9),
    summary="Data analytics student who turns messy data into dashboards and clear recommendations.",
    skills=["Languages: Python, SQL", "Analytics: Pandas, NumPy, Seaborn", "BI: Tableau, Power BI, Excel",
            "Concepts: A/B Testing, Statistics"],
    projects=[("Retail Sales Dashboard", ["Built a Tableau dashboard over 120,000 transaction rows",
                                          "Cleaned the source data with Pandas and SQL before loading",
                                          "Identified the 3 best-selling product categories by region"]),
              ("A/B Test Analysis", ["Analyzed a 20,000-user experiment with Python and Seaborn",
                                     "Calculated significance with a two-sample test"])],
    experience=[("Data Analyst Intern, Sample Retail Co", "Jun 2024 - Aug 2024",
                 ["Automated a weekly Excel report with Python, saving about 3 hours each week",
                  "Created 5 Power BI visuals for the sales team"])],
    education=["B.Sc Statistics, Sample University, 2022 - 2025"],
)

# ------------------------------------------------------------ EXCELLENT
R["excellent/01"] = dict(
    name="Sample Candidate 10", contact=contact(10),
    summary="Machine learning engineer in training with experience shipping NLP and tabular models, from data cleaning to "
            "Dockerized deployment. Reduced inference latency by 35% in a production prototype.",
    skills=["Languages: Python, SQL", "ML: Scikit-learn, XGBoost, PyTorch, Hugging Face Transformers",
            "Data: NumPy, Pandas, Matplotlib", "MLOps: Docker, MLflow, FastAPI, Git"],
    experience=[("Machine Learning Intern, Sample Analytics Pvt Ltd", "Jun 2024 - Aug 2024",
                 ["Built a demand-forecasting model with XGBoost that cut weekly forecast error by 18%",
                  "Cleaned and merged 3 SQL tables totaling 2M rows using Pandas",
                  "Tracked 40 experiments in MLflow, which made results reproducible for a team of 6",
                  "Deployed the model behind a FastAPI service packaged with Docker"])],
    projects=[("Resume Classifier", ["Fine-tuned a Hugging Face Transformers model on 8,000 labeled resumes, reaching 91% F1",
                                     "Reduced inference latency by 35% by exporting the PyTorch model and batching requests",
                                     "Served predictions through a FastAPI endpoint handling 50 requests per minute"]),
              ("Customer Churn Prediction", ["Built a Scikit-learn and XGBoost pipeline on 7,000 customers, improving recall by 12%",
                                             "Engineered 15 features with Pandas and Matplotlib error analysis",
                                             "Tracked every run with MLflow and Git"]),
              ("Document Search Engine", ["Implemented semantic search over 1,200 PDFs with Transformers embeddings",
                                          "Improved top-5 retrieval accuracy from 62% to 81% with query expansion"])],
    education=["B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026 | CGPA 8.7/10"],
    extra=[("CERTIFICATIONS AND ACHIEVEMENTS", ["Machine Learning Specialization, Sample Online Academy",
                                                "Ranked 12th of 400 teams in a university ML hackathon"])],
)
R["excellent/02"] = dict(
    name="Sample Candidate 11", contact=contact(11),
    summary="Full-stack developer who ships React and Node.js applications with automated tests and containerized "
            "deployments. Built an app now used by 300 students.",
    skills=["Languages: JavaScript, TypeScript, Python, SQL", "Frontend: React, Redux, HTML, CSS",
            "Backend: Node.js, Express, MongoDB, PostgreSQL", "DevOps: Docker, GitHub Actions, Git, Postman"],
    experience=[("Full-Stack Intern, Sample Web Studio", "May 2024 - Jul 2024",
                 ["Implemented a React and Redux checkout flow that raised completed orders by 9%",
                  "Reduced page load time by 40% by code-splitting and compressing images",
                  "Fixed 25 production bugs across the Node.js API and React front end",
                  "Automated tests and builds with GitHub Actions, cutting release time from 2 hours to 20 minutes"])],
    projects=[("Campus Marketplace", ["Developed a React and Node.js marketplace used by 300 students in the first month",
                                      "Designed 14 REST endpoints in Express with PostgreSQL and JWT authentication",
                                      "Containerized the stack with Docker and deployed it using GitHub Actions"]),
              ("Task Board", ["Built a drag-and-drop board in React with TypeScript and Redux",
                              "Wrote 60 unit tests, reaching 85% code coverage"]),
              ("Expense Tracker", ["Created a MongoDB-backed tracker serving 40 users with Postman-tested APIs",
                                   "Reduced API response time by 30% by adding database indexes"])],
    education=["B.Tech Computer Science, Sample Institute of Technology, 2022 - 2026 | CGPA 8.4/10"],
    extra=[("CERTIFICATIONS AND ACHIEVEMENTS", ["Full-Stack Web Development Certificate, Sample Online Academy",
                                                "Finalist, university web development contest (top 10 of 150)"])],
)
R["excellent/03"] = dict(
    name="Sample Candidate 12", contact=contact(12),
    summary="Data analyst who turns messy data into dashboards and decisions. Identified a pricing change that lifted "
            "monthly revenue by 6% in an internship project.",
    skills=["Languages: Python, SQL, R", "Analytics: Pandas, NumPy, Seaborn, Statsmodels",
            "BI: Tableau, Power BI, Excel", "Concepts: A/B Testing, Regression, Forecasting"],
    experience=[("Data Analyst Intern, Sample Retail Co", "Jun 2024 - Aug 2024",
                 ["Analyzed 500,000 transactions with SQL and Pandas to find underpriced products",
                  "Recommended a pricing change that lifted monthly revenue by 6%",
                  "Automated a weekly Excel report with Python, saving 3 hours per week",
                  "Built 8 Power BI visuals adopted by a sales team of 15"])],
    projects=[("Retail Sales Dashboard", ["Built a Tableau dashboard over 120,000 rows with region and product drill-downs",
                                          "Cleaned the source data with Pandas and SQL, removing 4% duplicate records",
                                          "Identified the 3 categories driving 55% of sales"]),
              ("A/B Test Analysis", ["Analyzed a 20,000-user experiment with Python, Seaborn and Statsmodels",
                                     "Showed a 2.1 point conversion lift with 95% confidence"]),
              ("Demand Forecasting", ["Forecasted weekly demand with regression in R, reaching 8% MAPE",
                                      "Compared 3 models and documented assumptions for stakeholders"])],
    education=["B.Sc Statistics, Sample University, 2022 - 2025 | CGPA 8.9/10"],
    extra=[("CERTIFICATIONS", ["Google Data Analytics Certificate", "Tableau Desktop Specialist"])],
)

if __name__ == "__main__":
    for key, data in R.items():
        tier, num = key.split("/")
        folder = os.path.join(OUT, tier)
        os.makedirs(folder, exist_ok=True)
        build(os.path.join(folder, f"{tier}_{num}.pdf"), data)
    print(f"Created {len(R)} resumes in {OUT}")
