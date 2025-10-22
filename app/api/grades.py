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
            grade_data = {
                "subject": g.get("subject"),
                "marks": g.get("marks"),
                "teacherName": g.get("teacherName"),
                "uploadedAt": g.get("uploadedAt").isoformat() if g.get("uploadedAt") else None,
                "fileName": g.get("fileName", "Unknown File"),
                "date": g.get("date"),
                "semester": g.get("semester"),
                "department": g.get("department"),
                "testType": g.get("testType"),
                "uploadId": g.get("uploadId")  # For grouping grades by upload
            }
            
            # Add CAT-specific fields
            if g.get("totalMarks") is not None:
                grade_data["totalMarks"] = g.get("totalMarks")
                grade_data["marksObtained"] = g.get("marks")
            
            # Add semester GPA field
            if g.get("gpa") is not None:
                grade_data["gpa"] = g.get("gpa")
            
            result.append(grade_data)
        
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
    Supports three formats:
    1. CAT: RegNo, Subject, MarksObtained, TotalMarks
    2. Semester: RegNo, Semester, GPA
    3. Regular: RegNo, Subject, Marks
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

        # Detect upload type and process accordingly
        is_cat_format = False
        is_semester_format = False
        
        # Check for CAT format (has totalMarks column)
        # CAT format includes: CAT-1, CAT-2, CAT-3, Mid-Semester, Internal
        total_marks_col = _find_column(df.columns, ["total", "totalmarks", "total_marks", "outof", "out_of", "maximum"])
        if total_marks_col and any(test in test_type for test in ["CAT", "Mid-Semester", "Internal"]):
            is_cat_format = True
        
        # Check for Semester GPA format
        gpa_col = _find_column(df.columns, ["gpa", "grade", "gradepoint", "grade_point"])
        if gpa_col and any(sem in test_type for sem in ["Semester", "semester"]):
            is_semester_format = True

        # Common columns
        roll_col = _find_column(df.columns, ["roll", "reg", "regno", "reg_number", "registration", "registerno"])
        
        if not roll_col:
            return jsonify({"success": False, "message": "Missing column: Registration Number (RegNo/Roll)"}), 400

        uploaded_time = datetime.datetime.utcnow()
        upload_id = str(datetime.datetime.utcnow().timestamp())  # Unique ID for this upload batch
        inserted = 0

        # Process based on format type
        if is_semester_format:
            # SEMESTER GPA FORMAT
            print(f"Processing Semester GPA format for {test_type}")
            
            if not gpa_col:
                return jsonify({"success": False, "message": "GPA column not found for semester upload"}), 400

            for idx, row in df.iterrows():
                raw_roll = row.get(roll_col)
                raw_gpa = row.get(gpa_col)

                if pd.isna(raw_roll) or pd.isna(raw_gpa):
                    continue

                rollno = str(raw_roll).strip()
                
                # Convert GPA to float
                try:
                    gpa_value = float(str(raw_gpa).strip())
                except:
                    continue

                # Find student
                student = current_app.db.users.find_one({"regNumber": rollno, "role": "student"})
                if not student:
                    continue

                # Insert semester GPA record
                current_app.db.grades.insert_one({
                    "studentId": student["user_id"],
                    "regNumber": rollno,
                    "subject": f"Semester {semester} GPA",  # Virtual subject name
                    "gpa": gpa_value,
                    "marks": gpa_value,  # Store GPA in marks field too for compatibility
                    "teacherId": teacher_id,
                    "teacherName": teacher_name,
                    "uploadedAt": uploaded_time,
                    "uploadId": upload_id,
                    "fileName": filename,
                    "date": date,
                    "semester": semester,
                    "department": department,
                    "testType": test_type,
                    "gradeType": "semester_gpa"
                })
                inserted += 1

        elif is_cat_format:
            # CAT FORMAT WITH TOTAL MARKS
            print(f"Processing CAT format with total marks for {test_type}")
            
            subject_col = _find_column(df.columns, ["subject", "sub"])
            marks_col = _find_column(df.columns, ["mark", "score", "marks", "obtained", "marksobtained", "marks_obtained"])
            
            if not subject_col:
                return jsonify({"success": False, "message": "Missing column: Subject"}), 400
            if not marks_col:
                return jsonify({"success": False, "message": "Missing column: Marks Obtained"}), 400
            if not total_marks_col:
                return jsonify({"success": False, "message": "Missing column: Total Marks"}), 400

            for idx, row in df.iterrows():
                raw_roll = row.get(roll_col)
                raw_subject = row.get(subject_col)
                raw_marks = row.get(marks_col)
                raw_total = row.get(total_marks_col)

                if pd.isna(raw_roll) or pd.isna(raw_subject) or pd.isna(raw_marks) or pd.isna(raw_total):
                    continue

                rollno = str(raw_roll).strip()
                subject = str(raw_subject).strip()
                
                # Convert marks to numeric
                try:
                    marks_obtained = float(str(raw_marks).strip())
                    total_marks = float(str(raw_total).strip())
                except:
                    continue

                # Find student
                student = current_app.db.users.find_one({"regNumber": rollno, "role": "student"})
                if not student:
                    continue

                # Insert CAT grade with total marks
                current_app.db.grades.insert_one({
                    "studentId": student["user_id"],
                    "regNumber": rollno,
                    "subject": subject,
                    "marks": marks_obtained,
                    "totalMarks": total_marks,
                    "teacherId": teacher_id,
                    "teacherName": teacher_name,
                    "uploadedAt": uploaded_time,
                    "uploadId": upload_id,
                    "fileName": filename,
                    "date": date,
                    "semester": semester,
                    "department": department,
                    "testType": test_type,
                    "gradeType": "cat_with_total"
                })
                inserted += 1

        else:
            # REGULAR FORMAT (backward compatibility)
            print(f"Processing regular format for {test_type}")
            
            subject_col = _find_column(df.columns, ["subject", "sub"])
            marks_col = _find_column(df.columns, ["mark", "score", "marks", "marks_obtained"])

            if not subject_col:
                return jsonify({"success": False, "message": "Missing column: Subject"}), 400
            if not marks_col:
                return jsonify({"success": False, "message": "Missing column: Marks"}), 400

            for idx, row in df.iterrows():
                raw_roll = row.get(roll_col)
                raw_subject = row.get(subject_col)
                raw_marks = row.get(marks_col)

                if pd.isna(raw_roll) or pd.isna(raw_subject) or pd.isna(raw_marks):
                    continue

                rollno = str(raw_roll).strip()
                subject = str(raw_subject).strip()

                # Convert marks to numeric
                try:
                    marks_numeric = float(str(raw_marks).strip())
                except:
                    continue

                # Find student
                student = current_app.db.users.find_one({"regNumber": rollno, "role": "student"})
                if not student:
                    continue

                # Insert regular grade
                current_app.db.grades.insert_one({
                    "studentId": student["user_id"],
                    "regNumber": rollno,
                    "subject": subject,
                    "marks": marks_numeric,
                    "teacherId": teacher_id,
                    "teacherName": teacher_name,
                    "uploadedAt": uploaded_time,
                    "uploadId": upload_id,
                    "fileName": filename,
                    "date": date,
                    "semester": semester,
                    "department": department,
                    "testType": test_type,
                    "gradeType": "regular"
                })
                inserted += 1

        if inserted == 0:
            return jsonify({"success": False, "message": "No valid grades were found in the file"}), 400

        format_type = "Semester GPA" if is_semester_format else ("CAT with Total Marks" if is_cat_format else "Regular")
        return jsonify({
            "success": True, 
            "message": f"{inserted} grades uploaded successfully",
            "format": format_type,
            "uploadId": upload_id
        }), 200

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
        
        # Fetch all uploads by this teacher grouped by uploadId
        docs = list(current_app.db.grades.find({"teacherId": teacher_id}))
        
        # Group by uploadId to get unique uploads
        history_map = {}
        for g in docs:
            upload_id = g.get("uploadId", g.get("fileName"))  # Fallback to fileName for old records
            
            if upload_id not in history_map:
                history_map[upload_id] = {
                    "uploadId": upload_id,
                    "fileName": g.get("fileName", "Unknown File"),
                    "date": g.get("date"),
                    "semester": g.get("semester"),
                    "department": g.get("department"),
                    "testType": g.get("testType"),
                    "uploadedAt": g.get("uploadedAt"),
                    "gradeCount": 0
                }
            
            history_map[upload_id]["gradeCount"] += 1
            
            # Keep the latest uploadedAt
            if g.get("uploadedAt") and (not history_map[upload_id]["uploadedAt"] or 
                                        g.get("uploadedAt") > history_map[upload_id]["uploadedAt"]):
                history_map[upload_id]["uploadedAt"] = g.get("uploadedAt")

        result = []
        for v in history_map.values():
            result.append({
                "uploadId": v["uploadId"],
                "fileName": v["fileName"],
                "date": v["date"],
                "semester": v["semester"],
                "department": v["department"],
                "testType": v["testType"],
                "uploadedAt": v["uploadedAt"].isoformat() if v["uploadedAt"] else None,
                "gradeCount": v["gradeCount"]
            })

        # Sort by uploadedAt descending
        result.sort(key=lambda x: x["uploadedAt"] if x["uploadedAt"] else "", reverse=True)

        return jsonify({"success": True, "files": result}), 200
    
    except Exception as e:
        print(f"Error fetching upload history: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ================= TEACHER: delete upload =================
@teacher_bp.route("/delete_upload/<upload_id>", methods=["DELETE"])
@jwt_required()
def delete_upload(upload_id):
    """Delete all grades from a specific upload"""
    try:
        teacher_id = get_jwt_identity()
        
        # Verify that this upload belongs to the teacher
        first_grade = current_app.db.grades.find_one({
            "uploadId": upload_id,
            "teacherId": teacher_id
        })
        
        if not first_grade:
            return jsonify({"success": False, "message": "Upload not found or unauthorized"}), 404

        # Delete all grades with this uploadId
        result = current_app.db.grades.delete_many({
            "uploadId": upload_id,
            "teacherId": teacher_id
        })

        deleted_count = result.deleted_count
        
        if deleted_count > 0:
            print(f"Deleted {deleted_count} grades for upload {upload_id} by teacher {teacher_id}")
            return jsonify({
                "success": True, 
                "message": f"Successfully deleted {deleted_count} grades"
            }), 200
        else:
            return jsonify({"success": False, "message": "No grades found to delete"}), 404

    except Exception as e:
        print(f"Error deleting upload: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ================= TEACHER: get upload details =================
@teacher_bp.route("/upload_details/<upload_id>", methods=["GET"])
@jwt_required()
def upload_details(upload_id):
    """Get detailed information about a specific upload"""
    try:
        teacher_id = get_jwt_identity()
        
        # Fetch all grades for this upload
        grades = list(current_app.db.grades.find({
            "uploadId": upload_id,
            "teacherId": teacher_id
        }))
        
        if not grades:
            return jsonify({"success": False, "message": "Upload not found"}), 404

        # Format grades for display
        result = []
        for g in grades:
            grade_info = {
                "regNumber": g.get("regNumber"),
                "subject": g.get("subject"),
                "marks": g.get("marks"),
            }
            
            # Add CAT-specific fields
            if g.get("totalMarks") is not None:
                grade_info["totalMarks"] = g.get("totalMarks")
            
            # Add GPA field
            if g.get("gpa") is not None:
                grade_info["gpa"] = g.get("gpa")
            
            result.append(grade_info)

        upload_info = grades[0] if grades else {}
        
        return jsonify({
            "success": True,
            "uploadInfo": {
                "uploadId": upload_id,
                "fileName": upload_info.get("fileName"),
                "date": upload_info.get("date"),
                "semester": upload_info.get("semester"),
                "department": upload_info.get("department"),
                "testType": upload_info.get("testType"),
                "uploadedAt": upload_info.get("uploadedAt").isoformat() if upload_info.get("uploadedAt") else None,
                "gradeType": upload_info.get("gradeType", "regular")
            },
            "grades": result,
            "totalGrades": len(result)
        }), 200

    except Exception as e:
        print(f"Error fetching upload details: {e}")
        return jsonify({"success": False, "message": str(e)}), 500