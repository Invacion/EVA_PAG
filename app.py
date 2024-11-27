from difflib import SequenceMatcher
import re
import os
from flask import Flask, render_template, request, redirect 
from pydub import AudioSegment
import speech_recognition as sr
from googletrans import Translator  # Importamos el traductor

app = Flask(__name__)

# Carpeta para almacenar los archivos subidos
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Asegúrate de que la carpeta exista
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

def clean_text(text):
    # Eliminar signos de puntuación y convertir a minúsculas
    text = re.sub(r'[^\w\s]', '', text)  # Eliminar todo excepto letras y espacios
    text = text.lower()  # Convertir a minúsculas
    return text

def replace_synonyms(text, synonyms_dict):
    # Reemplazar sinónimos en el texto
    for key, synonyms in synonyms_dict.items():
        for synonym in synonyms:
            text = text.replace(synonym, key)
    return text

def are_synonyms(word1, word2, synonyms_dict):
    # Comprobar si las palabras son sinónimos
    return (word1 in synonyms_dict and word2 in synonyms_dict[word1]) or \
        (word2 in synonyms_dict and word1 in synonyms_dict[word2])

def calculate_difference_and_print_changes(text1, text2, synonyms_dict):
    # Limpiar los textos
    cleaned_text1 = clean_text(text1)
    cleaned_text2 = clean_text(text2)

    # Reemplazar sinónimos en los textos
    cleaned_text1 = replace_synonyms(cleaned_text1, synonyms_dict)
    cleaned_text2 = replace_synonyms(cleaned_text2, synonyms_dict)

    # Dividir los textos en palabras
    words1 = cleaned_text1.split()
    words2 = cleaned_text2.split()

    # Usar SequenceMatcher para calcular las diferencias
    matcher = SequenceMatcher(None, words1, words2)
    differences = matcher.get_opcodes()

    # Calcular el número de diferencias
    num_differences = 0
    changes = []

    for tag, i1, i2, j1, j2 in differences:
        if tag == 'replace':
            # Si hay un reemplazo, imprime las palabras cambiadas
            for i in range(i1, i2):
                if not are_synonyms(words1[i], words2[j1], synonyms_dict):
                    changes.append(f"{words1[i]} --> {words2[j1]}")
                    num_differences += 1
                j1 += 1
        elif tag == 'delete':
            for i in range(i1, i2):
                changes.append(f"{words1[i]} --> (deleted)")
                num_differences += 1
        elif tag == 'insert':
            for j in range(j1, j2):
                changes.append(f"(inserted) --> {words2[j]}")
                num_differences += 1

    # Calcular el porcentaje de diferencia
    total_length = max(len(words1), len(words2))
    if total_length > 0:
        percentage_difference = (num_differences / total_length) * 100
    else:
        percentage_difference = 0.0  # Evitar división por cero

    # Clasificación del porcentaje de cambio
    if percentage_difference == 0:
        change_level = "Excelente 5/5"
    elif percentage_difference <= 20:
        change_level = "Muy bien 4/5"
    elif percentage_difference <= 60:
        change_level = "Bien 3/5"
    elif percentage_difference <= 60:
        change_level = "Satisfactorio 2/5"
    else:
        change_level = "Insuficiente 1/5"  # En caso de que sea más del 60% de diferencia

    return percentage_difference, change_level

# Definir un diccionario de sinónimos
synonyms_dict = {
    "i am": ["im", "i'm"],
    "im": ["i am", "i'm"],
    "happy": ["glad", "joyful"]
}

# Función para obtener la duración del archivo de audio
def get_audio_duration(filepath):
    # Cargar el archivo de audio
    audio = AudioSegment.from_file(filepath)
    # Obtener la duración en segundos
    duration_seconds = len(audio) / 1000.0  # Pydub da la duración en milisegundos, lo convertimos a segundos
    return duration_seconds

# Función para calcular la fluidez
def calculate_fluency(transcription, audio_filepath):
    # Contamos el número de palabras en la transcripción
    num_words = len(transcription.split())

    # Obtener la duración del audio
    audio_duration = get_audio_duration(audio_filepath)

    # Convertir la duración del audio a minutos
    audio_duration_minutes = audio_duration / 60.0

    # Calcular la fluidez en palabras por minuto
    if audio_duration_minutes > 0:
        fluency = num_words / audio_duration_minutes
    else:
        fluency = 0

    # Calificar la fluidez
    if fluency >= 50:
        fluency_level = "Excelente 5/5"
    elif fluency >= 40:
        fluency_level = "Muy bien 4/5"
    elif fluency >= 30:
        fluency_level = "Bien 3/5"
    elif fluency >= 10:
        fluency_level = "Satisfactorio 2/5"
    else:
        fluency_level = "Insuficiente 1/5"  # En caso de que haya menos de 10 palabras por minuto

    return fluency, fluency_level

@app.route('/upload', methods=['POST'])
def upload_file():
    # Verificar si se subió un archivo
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        return redirect(request.url)

    if file:
        # Guardar el archivo subido en la carpeta 'uploads'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        # Transcribir el audio
        transcription = transcribe_audio(filepath)

        # Traducir el texto al español y luego al inglés
        translated_text = translate_text(transcription)

        # Calcular el porcentaje de diferencia y las palabras cambiadas
        percentage_difference, changes = calculate_difference_and_print_changes(
            transcription, translated_text['english'], synonyms_dict
        )

        # Calcular la fluidez
        fluency = calculate_fluency(transcription, filepath)

        # Pasar la transcripción, las traducciones, el porcentaje de diferencia, los cambios y la fluidez a la plantilla 'result.html'
        return render_template('result.html', transcription=transcription, 
                               translated_text=translated_text, 
                               change_percentage=percentage_difference,
                               changes=changes, fluency=fluency)

def calculate_changes_percentage(original_text, translated_text):
    # Usamos difflib para comparar los dos textos
    sequence_matcher = SequenceMatcher(None, original_text, translated_text)
    # Calculamos la proporción de similitud
    similarity = sequence_matcher.ratio()
    # Calculamos el porcentaje de diferencia
    change_percentage = (1 - similarity) * 100
    return change_percentage

def transcribe_audio(filepath):
    recognizer = sr.Recognizer()
    audio_file = sr.AudioFile(filepath)

    with audio_file as source:
        audio = recognizer.record(source)  # Graba todo el contenido del archivo

    try:
        # Usamos el reconocimiento de Google para transcribir el audio
        transcription = recognizer.recognize_google(audio, language="en-US")
        print("Texto transcrito:", transcription)

        # Llamamos a la función para agregar signos de interrogación y puntos
        result = add_question_marks(transcription)
        print("Texto corregido v2:", result) 
        return result

    except sr.UnknownValueError:
        return "No se pudo entender el audio."
    except sr.RequestError:
        return "Hubo un error al contactar el servicio de transcripción."

def translate_text(text):
    translator = Translator()

    # Traducir el texto al español
    translated_to_spanish = translator.translate(text, src='en', dest='es').text
    print("Texto traducido al español:", translated_to_spanish)

    # Traducir el texto al inglés
    translated_to_english = translator.translate(translated_to_spanish, src='es', dest='en').text
    print("Texto traducido al inglés:", translated_to_english)

    return {'spanish': translated_to_spanish, 'english': translated_to_english}

def add_question_marks(text):
    question_words_combinations = [
        ("why", ["I", "you", "he", "she", "it"]),
        ("where", ["I", "are", "you", "he"]),
        ("what", ["is", "goes", "works"]),
    ]

    # Lista de pronombres y sus combinaciones
    pronouns_combinations = [
        ("I'm", ["going", "working", "here"]),
        ("you're", ["going", "working", "here"]),                
        ("we", ["are", "go", "work"])
    ]

    # Construir la expresión regular a partir de la lista de combinaciones de pronombres
    pronouns_pattern = "|".join([f"\\b{pronoun} ({'|'.join(combinations)})" for pronoun, combinations in pronouns_combinations])

    # Extraer las palabras de pregunta de la lista de combinaciones
    question_words = [pair[0] for pair in question_words_combinations]
    question_words_pattern = "|".join(question_words)

    # Primero agregamos signos de interrogación donde corresponde
    match = re.search(rf"({question_words_pattern})(.*?)(\b{pronouns_pattern}\b)", text)

    if match:
        # Buscar el índice en el que comienza el pronombre
        pronoun_start_index = match.start(3)

        # Verificar que el índice se haya encontrado
        if pronoun_start_index != -1:
            # Buscar el índice antes de un espacio antes del pronombre
            question_mark_position = pronoun_start_index - 1

            # Insertar el signo de interrogación justo antes del pronombre
            modified_text = text[:question_mark_position] + "?" + text[question_mark_position:]
            return modified_text  # Retornar el texto modificado
        else:
            return text
    else:
        # Buscar las palabras de pregunta al principio de la oración sin pronombres
        question_match = re.search(rf"({question_words_pattern})\b(.*)", text)

        if question_match:
            question_word = question_match.group(1)
            rest_of_text = question_match.group(2).strip()

            # Si no hay un pronombre después de la palabra de pregunta
            if not re.search(pronouns_pattern, rest_of_text):
                # Agregar el signo de interrogación al final
                text = text + "?"
            else:
                # Si ya hay un pronombre, dejamos el texto igual
                return text

    # Añadir puntos en otros lugares donde corresponda
    for pronoun, combinations in pronouns_combinations:
        for combination in combinations:
            # Buscar coincidencias de pronombre + verbo
            text = re.sub(rf"(\b{pronoun} {combination}\b)(?!\?)", r". \1", text)

    # Añadir un solo punto antes de la palabra de pregunta, si no está precedida de uno
    text = re.sub(rf"(?<!\.)\s*(?=\b{question_words_pattern}\b)", ".", text)

    # Reemplazar puntos consecutivos por un solo punto
    text = re.sub(r"\.\.+", ".", text)

    # Asegurar que haya un espacio después de cada punto
    text = re.sub(r"(\.)(?=\S)", r". ", text)

    # Eliminar espacios innecesarios antes del punto
    text = re.sub(r"\s+\.", ".", text)

    # Eliminar punto al inicio si existe
    text = text.lstrip(".").lstrip()
    
    return text


