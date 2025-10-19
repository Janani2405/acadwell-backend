# backend/app/api/grades.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import pandas as pd
import datetime
from io import BytesIO

students_bp = Blueprint("students_bp", __name__)
teacher_bp = Blueprint("teacher_bp", __name__)

ALLOWED_EXTENSIONS = {"csv", "xlsx"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _find_column(df_cols, candidates):
    """Return the first column name in df_cols that contains any candidate token."""
    for c in df_cols:
        for cand in candidates:
            if cand.lower() in c.lower():
                return c
    return None

# ================= STUDENT: fetch my grades =================
@students_bp.route("/my_grades", methods=["GET"])
@jwt_required()
def my_grades():
    """Fetch grades for the logged-in student"""
    try:
        student_id = get_jwt_identity()
        student = current_app.db.users.find_one({"user_id": student_id, "role": "student"})
        
        if not student:
            return jsonify({"success": False, "message": "Student not found"}), 404

        reg_no = student.get("regNumber")
        if not reg_no:
            return jsonify({"success": False, "message": "Student has no registration number"}), 400

        # fetch only documents for this student's regNumber
        grades = list(current_app.db.grades.find({"regNumber": reg_no}))
        result = []
        
        for g in grades:
            result.append({
                "subject": g.get("subject"),
                "marks": g.get("marks"),
                "teacherName": g.get("teacherName"),
                "uploadedAt": g.get("uploadedAt").isoformat() if g.get("uploadedAt") else None,
                "fileName": g.get("fileName", "Unknown File"),
                "date": g.get("date"),
                "semester": g.get("semester"),
                "department": g.get("department"),
                "testType": g.get("testType")
            })
        
        return jsonify({"success": True, "grades": result}), 200
    
    except Exception as e:
        print(f"Error fetching grades: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ================= TEACHER: upload grades =================
@teacher_bp.route("/upload_grades", methods=["POST"])
@jwt_required()
def upload_grades():
    """
    Upload grades from CSV or Excel file
    Expects multipart/form-data:
      - file: .csv or .xlsx (with rollno, subject, marks columns)
      - date, semester, department, testType (as form fields)
    """
    try:
        teacher_id = get_jwt_identity()
        teacher = current_app.db.users.find_one({"user_id": teacher_id, "role": "teacher"})
        
        if not teacher:
            return jsonify({"success": False, "message": "Teacher not found"}), 404
        
        teacher_name = teacher.get("name", "Unknown Teacher")

        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file_storage = request.files["file"]
        if file_storage.filename == "" or not allowed_file(file_storage.filename):
            return jsonify({"success": False, "message": "Invalid or missing file. Use CSV or XLSX"}), 400

        # form metadata
        date = request.form.get("date")
        semester = request.form.get("semester")
        department = request.form.get("department")
        test_type = request.form.get("testType")

        if not all([date, semester, department, test_type]):
            return jsonify({"success": False, "message": "All fields (date, semester, department, testType) are required"}), 400

        filename = secure_filename(file_storage.filename)

        # Read file contents safely into pandas using BytesIO
        file_bytes = file_storage.read()
        buf = BytesIO(file_bytes)

        # Read CSV or Excel
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(buf, dtype=str)
        else:
            df = pd.read_excel(buf, dtype=str)

        if df.empty:
            return jsonify({"success": False, "message": "Uploaded file is empty"}), 400

        # Normalize column names for robust matching
        df.columns = [str(c).strip().lower() for c in df.columns]

        # Tolerant column detection
        roll_col = _find_column(df.columns, ["roll", "reg", "regno", "reg_number", "registration"])
        subject_col = _find_column(df.columns, ["subject", "sub"])
        marks_col = _find_column(df.columns, ["mark", "score", "marks", "marks_obtained"])

        missing = []
        if not roll_col:
            missing.append("rollno/regno")
        if not subject_col:
            missing.append("subject")
        if not marks_col:
            missing.append("marks")

        if missing:
            return jsonify({"success": False, "message": f"Missing columns: {', '.join(missing)}"}), 400

        uploaded_time = datetime.datetime.utcnow()
        inserted = 0

        # Process each row
        for idx, row in df.iterrows():
            raw_roll = row.get(roll_col)
            raw_subject = row.get(subject_col)
            raw_marks = row.get(marks_col)

            # Skip incomplete rows
            if pd.isna(raw_roll) or pd.isna(raw_subject) or pd.isna(raw_marks):
                continue

            rollno = str(raw_roll).strip()
            subject = str(raw_subject).strip()
            marks_val = raw_marks

            # Try to convert marks to numeric
            try:
                if isinstance(marks_val, str):
                    marks_val = marks_val.strip()
                    if marks_val == "":
                        continue
                    marks_numeric = float(marks_val) if any(ch.isdigit() for ch in marks_val) else marks_val
                else:
                    marks_numeric = float(marks_val)
            except Exception:
                marks_numeric = raw_marks

            # Find student by regNumber
            student = current_app.db.users.find_one({"regNumber": rollno, "role": "student"})
            if not student:
                # Skip unknown roll numbers
                continue

            # Insert grade document
            current_app.db.grades.insert_one({
                "studentId": student["user_id"],
                "regNumber": rollno,
                "subject": subject,
                "marks": marks_numeric,
                "teacherId": teacher_id,
                "teacherName": teacher_name,
                "uploadedAt": uploaded_time,
                "fileName": filename,
                "date": date,
                "semester": semester,
                "department": department,
                "testType": test_type
            })
            inserted += 1

        if inserted == 0:
            return jsonify({"success": False, "message": "No valid grades were found in the file"}), 400

        return jsonify({"success": True, "message": f"{inserted} grades uploaded successfully"}), 200

    except Exception as e:
        print(f"Error uploading grades: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ================= TEACHER: upload history =================
@teacher_bp.route("/my_uploads", methods=["GET"])
@jwt_required()
def my_uploads():
    """Fetch upload history for the logged-in teacher"""
    try:
        teacher_id = get_jwt_identity()
        
        # Fetch all uploads by this teacher
        docs = list(current_app.db.grades.find({"teacherId": teacher_id}))
        
        # Group by file metadata to show concise history
        history_map = {}
        for g in docs:
            key = (
                g.get("fileName", "Unknown File"),
                g.get("date"),
                g.get("semester"),
                g.get("department"),
                g.get("testType")
            )
            
            # Keep latest uploadedAt for each unique file
            existing = history_map.get(key)
            if not existing or (g.get("uploadedAt") and g.get("uploadedAt") > existing["uploadedAt"]):
                history_map[key] = {
                    "fileName": key[0],
                    "date": key[1],
                    "semester": key[2],
                    "department": key[3],
                    "testType": key[4],
                    "uploadedAt": g.get("uploadedAt")
                }

        result = []
        for v in history_map.values():
            result.append({
                "fileName": v["fileName"],
                "date": v["date"],
                "semester": v["semester"],
                "department": v["department"],
                "testType": v["testType"],
                "uploadedAt": v["uploadedAt"].isoformat() if v["uploadedAt"] else None
            })

        return jsonify({"success": True, "files": result}), 200
    
    except Exception as e:
        print(f"Error fetching upload history: {e}")
        return jsonify({"success": False, "message": str(e)}), 500