from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        # Optional header
        self.set_font('Arial', 'B', 12)
        self.set_text_color(11, 61, 145)
        self.cell(0, 10, 'SQL + PL/SQL Master Guide', ln=True, align='C')
        self.ln(5)

    def footer(self):
        # Page footer
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(0, 0, 0)
        self.cell(0, 10, 'Trainer: Raj Rana | Page ' + str(self.page_no()), 0, 0, 'C')

# Initialize PDF
pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=15)

# ---------------- Cover Page ----------------
pdf.add_page()
pdf.set_font("Arial", 'B', 24)
pdf.cell(0, 10, "SQL + PL/SQL Master Guide", ln=True, align='C')
pdf.set_font("Arial", '', 16)
pdf.ln(10)
pdf.multi_cell(0, 10, "Beginner to Pro — Complete Practical Training Guide\nHands-on SQL & PL/SQL for Real Projects and Interviews", align='C')
pdf.ln(20)
pdf.set_font("Arial", 'I', 14)
pdf.cell(0, 10, "Trainer: Raj Rana", ln=True, align='C')

# ---------------- Table of Contents ----------------
pdf.add_page()
pdf.set_font("Arial", 'B', 16)
pdf.cell(0, 10, "Table of Contents", ln=True)
pdf.set_font("Arial", '', 12)

# List of SQL chapters (1-75)
sql_chapters = [
    "Introduction to Databases",
    "SQL Basics: SELECT",
    "Filtering Data: WHERE",
    "ORDER BY and DISTINCT",
    "Joins: INNER, LEFT, RIGHT, FULL OUTER",
    "Aggregations: COUNT, SUM, AVG, MIN, MAX",
    "GROUP BY & HAVING",
    "Subqueries & Nested Queries",
    "SET Operators: UNION, INTERSECT, MINUS",
    "DDL Commands: CREATE, ALTER, DROP",
    "DML Commands: INSERT, UPDATE, DELETE",
    "Indexes, Views, Sequences",
    "Transactions & Concurrency",
    "Analytical Functions & Window Functions",
    "SQL Mini Project & Exercises"
] * 5  # Repeat to simulate 75 pages

# List of PL/SQL chapters (76-105)
plsql_chapters = [
    "PL/SQL Basics: Block Structure",
    "Variables and Data Types",
    "Control Structures: IF, LOOP, CASE",
    "Cursors: Implicit & Explicit",
    "Exception Handling",
    "Procedures & Functions",
    "Packages",
    "Triggers: DML Triggers",
    "Bulk Collect & FORALL",
    "Records & Collections",
    "Autonomous Transactions",
    "PL/SQL Mini Project & Exercises"
] * 3  # Repeat to simulate 30 pages

# Combine chapters
all_chapters = sql_chapters[:75] + plsql_chapters[:30]

# Print Table of Contents
for idx, chapter in enumerate(all_chapters, start=1):
    pdf.cell(0, 8, f"{idx}. {chapter}", ln=True)

# ---------------- Chapters ----------------
for idx, chapter in enumerate(all_chapters, start=1):
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Chapter {idx}: {chapter}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", '', 12)
    
    # Sample content per chapter (replace with full examples)
    content = f"This chapter covers: {chapter}\n\n"
    
    if "SQL" in chapter or "PL/SQL" in chapter or "SELECT" in chapter:
        content += "Example SQL/PLSQL:\n"
        content += "```sql\nSELECT * FROM employees;\n```\n\n"
    
    content += "Practice Exercises:\n"
    content += "- Exercise 1\n- Exercise 2\n- Exercise 3\n\n"
    
    pdf.multi_cell(0, 8, content)

# ---------------- Save PDF ----------------
pdf.output("SQL_PL_SQL_Master_Guide_105_Pages.pdf")
print("PDF Generated: SQL_PL_SQL_Master_Guide_105_Pages.pdf")
