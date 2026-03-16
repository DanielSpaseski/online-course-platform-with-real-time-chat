import requests
import json
import re
from django.conf import settings

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
except ImportError:
    import PyPDF2

    HAS_PDFPLUMBER = False


def extract_text_from_pdf(pdf_file):
    """Извлечи текст од PDF фајл"""
    try:
        pdf_file.seek(0)
        text = ""

        if HAS_PDFPLUMBER:
            # Користиме pdfplumber за подобра поддршка на кирилица
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        else:
            # Fallback на PyPDF2
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            for page in pdf_reader.pages:
                text += page.extract_text()

        pdf_file.seek(0)
        extracted = text.strip()

        print(f"Извлечен текст: {len(extracted)} карактери")
        print(f"Почеток: {extracted[:200]}...")

        return extracted if len(extracted) > 50 else None

    except Exception as e:
        print(f"Грешка при извлекување на текст: {e}")
        return None


def generate_quiz_from_text(text, num_questions=5):
    """Генерирај квиз со Groq API (Llama 3.3)"""

    api_key = getattr(settings, 'GEMINI_API_KEY', None)  # Користиме истиотклуч

    if not api_key:
        print("GEMINI_API_KEY не е сетиран (користиме Groq)")
        return generate_fallback_quiz(num_questions)

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Скрати го текстот ако е предолг
    max_chars = 3500
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    prompt = f"""Врз основа на следниот текст, генерирај точно {num_questions} прашања за квиз на македонски јазик.

ТЕКСТ:
{text}

ВАЖНИ БАРАЊА:
1. Прашањата МОРА да бидат базирани на текстот погоре
2. Секое прашање МОРА да има точно 4 одговори (А, Б, В, Г)
3. Само еден одговор е точен
4. Одговорите треба да бидат релевантни и логични
5. Не измислувај информации што не се во текстот

Форматирај го одговорот како JSON:

{{
  "questions": [
    {{
      "question_text": "Прашање на македонски базирано на текстот?",
      "explanation": "Кратко објаснување зошто ова е точниот одговор",
      "answers": [
        {{"answer_text": "Точен одговор базиран на текстот", "is_correct": true}},
        {{"answer_text": "Неточен одговор 1", "is_correct": false}},
        {{"answer_text": "Неточен одговор 2", "is_correct": false}},
        {{"answer_text": "Неточен одговор 3", "is_correct": false}}
      ]
    }}
  ]
}}

Врати САМО валиден JSON, без дополнителен текст."""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "Ти си експерт за креирање на едукативни квизови. Секогаш генерираш квизови со 4 одговори за секое прашање, каде што точно 1 е точен."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 2500,
        "response_format": {"type": "json_object"}
    }

    try:
        print(f"Праќам барање до Groq API...")
        response = requests.post(url, headers=headers, json=payload, timeout=45)

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']

            print(f"Примен одговор од API")
            print(f"Почеток на одговорот: {content[:200]}...")

            # Parse JSON
            quiz_data = json.loads(content)

            # Валидација
            if 'questions' not in quiz_data:
                print("JSON нема 'questions' клуч")
                return generate_fallback_quiz(num_questions)

            questions = quiz_data['questions']

            # Провери дали секое прашање има 4 одговори
            valid_questions = []
            for idx, q in enumerate(questions, 1):
                if 'answers' not in q or len(q['answers']) < 2:
                    print(f"Прашање {idx} нема доволно одговори, додавам...")
                    # Додај недостасувачки одговори
                    while len(q.get('answers', [])) < 4:
                        q.setdefault('answers', []).append({
                            "answer_text": f"Дополнителен одговор {len(q['answers']) + 1}",
                            "is_correct": False
                        })

                # Провери дали има барем еден точен одговор
                has_correct = any(a.get('is_correct') for a in q.get('answers', []))
                if not has_correct and q.get('answers'):
                    print(f"Прашање {idx} нема точен одговор, го означувам првиот")
                    q['answers'][0]['is_correct'] = True

                valid_questions.append(q)

            quiz_data['questions'] = valid_questions

            print(f"Валидирани {len(valid_questions)} прашања")
            return quiz_data

        else:
            print(f"API грешка: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return generate_fallback_quiz(num_questions)

    except requests.exceptions.Timeout:
        print("Timeout - API не одговори на време")
        return generate_fallback_quiz(num_questions)
    except json.JSONDecodeError as e:
        print(f"JSON parse грешка: {e}")
        return generate_fallback_quiz(num_questions)
    except Exception as e:
        print(f"Непозната грешка: {e}")
        import traceback
        traceback.print_exc()
        return generate_fallback_quiz(num_questions)


def generate_fallback_quiz(num_questions=5):
    """Fallback квиз ако API не работи"""
    print("Користам fallback квиз (AI не е достапен)")

    return {
        "questions": [
            {
                "question_text": f"Прашање {i + 1} (AI не беше достапен за генерирање)",
                "explanation": "Ова е автоматски генерирано прашање. Уредете го во admin панелот.",
                "answers": [
                    {"answer_text": "Одговор А", "is_correct": True},
                    {"answer_text": "Одговор Б", "is_correct": False},
                    {"answer_text": "Одговор В", "is_correct": False},
                    {"answer_text": "Одговор Г", "is_correct": False},
                ]
            }
            for i in range(num_questions)
        ]
    }