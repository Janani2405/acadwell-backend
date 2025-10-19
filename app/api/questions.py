from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import uuid

questions_bp = Blueprint('questions', __name__)

@questions_bp.route('', methods=['GET'])
def get_questions():
    try:
        if current_app.db is None:
            return jsonify({'error': 'Database not connected'}), 500

            
        questions = list(current_app.db.questions.find({}, {'_id': 0}).limit(10))
        return jsonify({
            'success': True,
            'questions': questions,
            'count': len(questions)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@questions_bp.route('', methods=['POST'])
def create_question():
    try:
        data = request.get_json()
        
        question = {
            'id': str(uuid.uuid4()),
            'title': data.get('title'),
            'content': data.get('content'),
            'tags': data.get('tags', []),
            'created_at': datetime.now(),
            'anonymous_id': data.get('anonymous_id')
        }
        
        if current_app.db is not None:
            current_app.db.questions.insert_one(question)

        
        return jsonify({
            'success': True,
            'question': question,
            'message': 'Question created successfully'
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500