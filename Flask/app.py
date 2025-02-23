import os
from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from haystack.nodes import PDFToTextConverter, PreProcessor, QuestionGenerator
from haystack.preprocessor import PreProcessor
from haystack.document_stores.faiss import FAISSDocumentStore
from haystack.retriever import DensePassageRetriever
from haystack.reader import FARMReader
from haystack.pipelines import (
    ExtractiveQAPipeline,
    QuestionGenerationPipeline,
    RetrieverQuestionGenerationPipeline,
    QuestionAnswerGenerationPipeline
)
from haystack.utils import print_questions
import tqdm
import xlsxwriter
import time

app = Flask(__name__)

app.config["ALLOWED_EXTENSIONS"] = set(["pdf"])
app.config["UPLOAD_FOLDERS"] = "uploads/"


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1] in app.config["ALLOWED_EXTENSIONS"]
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route('/question-answering')
def question_answering():
    return render_template('question-answering.html')


@app.route('/question-generator')
def question_generator():
    return render_template('question-generator.html')


@app.route('/prof-assist-studio', methods=['GET', 'POST'])
def prof_assist_studio():
    document = request.files["file"]
    if document and allowed_file(document.filename):
        filename = secure_filename(document.filename)
        document.filename.replace(' ', '_')
        document.save(os.path.join(app.config["UPLOAD_FOLDERS"], filename))
        prof_assist_studio.document_file = os.path.join(
            app.config["UPLOAD_FOLDERS"], filename)
        pdf_converter = PDFToTextConverter(
            remove_numeric_tables=True, valid_languages=["en"])
        converted = pdf_converter.convert(
            file_path=prof_assist_studio.document_file, meta={"company": "Company_1", "processed": False})
        preprocessor = PreProcessor(
            split_by="word", split_length=200, split_overlap=10)
        preprocessed = preprocessor.process(converted)
        document_store = FAISSDocumentStore(
            faiss_index_factory_str="Flat", return_embedding=True)
        document_store.delete_all_documents()
        document_store.write_documents(preprocessed)
        retriever = DensePassageRetriever(document_store=document_store)
        reader = FARMReader(
            model_name_or_path="deepset/tinyroberta-squad2", use_gpu=False)
        document_store.update_embeddings(retriever)
        prof_assist_studio.pipeline = ExtractiveQAPipeline(reader, retriever)
        return render_template("prof-assist-studio.html")


def preprocessing(file_path):
    pdf_converter = PDFToTextConverter(
        remove_numeric_tables=True, valid_languages=["en"])
    converted = pdf_converter.convert(file_path=file_path, meta={
                                      "company": "Company_1", "processed": False})
    preprocessor = PreProcessor(
        split_by="word", split_length=200, split_overlap=10)
    preprocessed = preprocessor.process(converted)
    return preprocessed


def document_store(document_preprocessed):
    document_store = FAISSDocumentStore(
        faiss_index_factory_str="Flat", return_embedding=True,)
    document_store.delete_all_documents()
    document_store.write_documents(document_preprocessed)
    return document_store


def question_generator_pipeline(document_store):
    reader = FARMReader(
        model_name_or_path='deepset/tinyroberta-squad2', use_gpu=True)
    question_generator = QuestionGenerator()
    qag_pipeline = QuestionAnswerGenerationPipeline(question_generator, reader)
    return qag_pipeline


def question_generator(document_store, qag_pipeline):
    row = 1
    column = 0
    timestr = time.strftime("%Y%m%d-%H%M%S")
    question_generator.filename_excel = timestr + '.xls'
    workbook = xlsxwriter.Workbook('static/'+question_generator.filename_excel)
    worksheet = workbook.add_worksheet('Sheet 1')
    worksheet.write(0, 0, 'Question')
    worksheet.write(0, 1, 'Answer')
    worksheet.write(0, 2, 'Context')
    for idx, document in enumerate(tqdm.tqdm(document_store)):
        res = qag_pipeline.run(documents=[document])
        for i in range(0, len(res['queries'])):
            # print('Question: ', res['queries'][i])
            query = res['queries'][i]
            worksheet.write(row, column, query)

            # print('Answer: ', res['answers'][i][0].answer)
            answer = res['answers'][i][0].answer
            worksheet.write(row, column + 1, answer)

            # print('Context: ', res['answers'][i][0].context)
            contexts = res['answers'][i][0].context
            worksheet.write(row, column + 2, contexts)
            row += 1
    workbook.close()


@app.route('/questions-result', methods=['GET', 'POST'])
def questions_result():
    document = request.files["file"]
    if document and allowed_file(document.filename):
        filename = secure_filename(document.filename)
        document.filename.replace(' ', '_')
        document.save(os.path.join(app.config["UPLOAD_FOLDERS"], filename))
        prof_assist_studio.document_file = os.path.join(app.config["UPLOAD_FOLDERS"], filename)
        preprocessed = preprocessing(prof_assist_studio.document_file)
        document_stores = document_store(preprocessed)
        qag_pipeline = question_generator_pipeline(document_stores)
        question_generator(document_stores, qag_pipeline)
    return render_template("questions-result.html")


@app.route('/download_excel')
def download_file():
    excel = 'static/'+question_generator.filename_excel
    return send_file(excel, as_attachment=True)


def chatbot_response(msg):
    answers = []
    context = []
    for i in range(5):
        answers.append(
            get_prof_assist_response.prediction["answers"][i].answer)
        context.append(
            get_prof_assist_response.prediction["answers"][i].context)
    result = '<strong>Answer 1: </strong>' + '{}'.format(answers[0]) + '<br><br>' + '<strong>Context:</strong> ' + context[0] + '....' + '<br><br>' \
             '<strong>Answer 2: </strong>' + '{}'.format(answers[1]) + '<br><br>' + '<strong>Context:</strong> ' + context[1] + '....' + '<br><br>' \
             '<strong>Answer 3: </strong>' + \
        '{}'.format(answers[2]) + '<br><br>' + \
        '<strong>Context:</strong> ' + context[2] + '....'
    return result


@app.route("/get")
def get_prof_assist_response():
    query = request.args.get("msg")
    if query == 'Hello':
        return "Hello! This is ProfAssist, the teacher's assistant for Students."
    get_prof_assist_response.prediction = prof_assist_studio.pipeline.run(
        query=query, params={"Retriever": {
            "top_k": 5}, "Reader": {"top_k": 10}}
    )
    return chatbot_response(query)


@app.route("/done")
def done():
    try:
        os.remove('faiss_document_store.db')
    except:
        pass
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
