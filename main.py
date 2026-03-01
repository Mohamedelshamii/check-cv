import os
import logging
import io
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configure Gemini API
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key and gemini_api_key != "your_gemini_api_key_here":
    genai.configure(api_key=gemini_api_key)
    logger.info("Gemini API initialized.")
else:
    logger.warning("GEMINI_API_KEY is not set or valid.")

# Define states for ConversationHandler
RECEIVE_CV, RECEIVE_JOB_LINK = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"مرحباً {user.mention_html()}! 👋"
        "\nأنا بوت مخصص لمساعدتك. الرجاء إرسال سيرتك الذاتية (CV) بصيغة PDF لنبدأ."
        "\n\n(لإلغاء العملية في أي وقت، يمكنك إرسال الأمر /cancel 🛑)"
    )
    return RECEIVE_CV

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("استخدم الأمر /start للبدء، وأرسل سيرتك الذاتية بصيغة PDF.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle incoming document (expected to be PDF), extract text and save it."""
    document = update.message.document
    if document.mime_type != 'application/pdf':
        await update.message.reply_text("عذراً، يرجى إرسال الملف بصيغة PDF فقط.")
        return RECEIVE_CV

    user = update.effective_user
    await update.message.reply_text("جاري استلام ومعالجة السيرة الذاتية... ⏳")
    
    # استخدام ملف مؤقت مخصص للمستخدم لتلافي التداخل وتوفير المساحة
    temp_file_path = f"temp_cv_{user.id}.pdf"
    
    try:
        # Download the file to a temporary file on the server
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(temp_file_path)
        
        # Read PDF content using PyPDF2
        pdf_reader = PdfReader(temp_file_path)
        text: str = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text = f"{text}{extracted}\n"
            
        # Save extracted text to user_data
        context.user_data['cv_text'] = text
        
        await update.message.reply_text(
            "تم استخراج النص من السيرة الذاتية بنجاح! ✅\n\n"
            "الخطوة التالية: يرجى إرسال رابط الوظيفة (Job Link) أو إرسال تفاصيل الوصف الوظيفي كنص مباشر.\n"
            "(تذكر: يمكنك إرسال /cancel لإلغاء العملية في أي وقت 🛑)"
        )
        return RECEIVE_JOB_LINK
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await update.message.reply_text("حدث خطأ أثناء معالجة ملف الـ PDF ❌. يرجى التأكد من الملف والمحاولة مرة أخرى.")
    finally:
        # حذف ملف الـ PDF المؤقت من الخادم لتوفير المساحة
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"Deleted temporary file: {temp_file_path} to save space.")
            
    return RECEIVE_CV

async def handle_job_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the job link or description text sent by the user."""
    text_input = update.message.text.strip()
    
    await update.message.reply_text("جاري معالجة بيانات الوظيفة المقترحة...")
    
    job_description = text_input
    
    # Check if the text is a link (basic validation)
    if text_input.startswith("http://") or text_input.startswith("https://"):
        try:
            # Setup headers to bypass basic bot protections
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            # Fetch the URL
            response = requests.get(text_input, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract plain text from the webpage
            parsed_text = soup.get_text(separator='\n', strip=True)
            if parsed_text and len(parsed_text) > 50:
                job_description = parsed_text
                await update.message.reply_text("تم جلب واستخراج الوصف الوظيفي من الرابط بنجاح! 🔗")
            else:
                raise ValueError("لم يتم العثور على نص كافٍ في الرابط.")
                
        except Exception as e:
            logger.warning(f"Failed to fetch or parse URL: {e}")
            await update.message.reply_text(
                "لم أتمكن من استخراج النص من الرابط (ربما يكون الرابط محمي ضد السحب التلقائي أو غير صالح).\n"
                "تم احتساب الرابط / النص المدخل كنص صريح للوصف الوظيفي."
            )
            job_description = text_input
    else:
        await update.message.reply_text("تم استلام النص ومعالجته كوصف وظيفي مباشر. 📝")

    # Store the job description in user_data
    context.user_data['job_description'] = job_description
    cv_text = context.user_data.get('cv_text', '')
    
    # إرسال رسالة انتظار تفاعلية 
    wait_message = await update.message.reply_text("جاري تحليل البيانات بالذكاء الاصطناعي، يرجى الانتظار ثواني... ⏳🤖")
    
    # Call Gemini to analyze
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = (
            "أنت خبير توظيف وأنظمة ATS. قارن بين هذه السيرة الذاتية وهذا الوصف الوظيفي. "
            "قم بالرد باللغة العربية بتنسيق واضح يحتوي على:\n"
            "1. نسبة القبول المتوقعة كنسبة مئوية (%).\n"
            "2. نقاط القوة والمطابقة.\n"
            "3. المهارات المفقودة.\n"
            "4. تعديلات مقترحة لرفع نسبة القبول.\n\n"
            f"--- السيرة الذاتية ---\n{cv_text}\n\n"
            f"--- الوصف الوظيفي ---\n{job_description}"
        )
        
        # Using async generation to prevent blocking the bot
        response = await model.generate_content_async(prompt)
        
        if response.text:
            text = response.text
            # Telegram's maximum message length is 4096 characters
            max_length = 4000 
            
            if len(text) > max_length:
                # تحديث رسالة الانتظار بالجزء الأول
                await wait_message.edit_text(text[:max_length])
                
                # إرسال باقي الأجزاء كرسائل جديدة
                for i in range(max_length, len(text), max_length):
                    await update.message.reply_text(text[i:i+max_length])
            else:
                # تحديث رسالة الانتظار بالنتيجة النهائية
                await wait_message.edit_text(text)
        else:
            await wait_message.edit_text("تعذر تحليل البيانات. قد يكون ذلك بسبب سياسات الأمان أو عدم اكتمال الرد.")
            
    except ValueError as e:
        logger.error(f"ValueError from Gemini (likely safety block): {e}")
        error_msg = (
            "عذراً، لم يتمكن الذكاء الاصطناعي من معالجة البيانات بسبب سياسات الحماية أو محتوى غير متوافق. 🚫\n"
            "يرجى مراجعة محتوى السيرة الذاتية أو الوصف الوظيفي والمحاولة مرة أخرى."
        )
        await wait_message.edit_text(error_msg)
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        error_msg = (
            "عذراً، يبدو أن الخادم لا يستجيب في الوقت الحالي أو أن حصة استخدام واجهة الذكاء الاصطناعي (API) قد انتهت. 😔\n"
            f"تفاصيل الخطأ: {str(e)}\n"
            "يرجى المحاولة مرة أخرى لاحقاً."
        )
        await wait_message.edit_text(error_msg)
    
    await update.message.reply_text("(انتهت المحادثة هنا. لإعادة الإرسال أو البدء من جديد، أرسل /start)")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("تم إلغاء المحادثة 🛑. يمكنك البدء من جديد بإرسال /start.")
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_TOKEN is not set properly in the .env file! Please update it.")
        return

    application = ApplicationBuilder().token(token).build()

    # Setup conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            RECEIVE_CV: [MessageHandler(filters.Document.ALL, handle_document)],
            RECEIVE_JOB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_job_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))

    # Run the bot
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
