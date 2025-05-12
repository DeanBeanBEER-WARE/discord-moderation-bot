"""Interface to the OpenAI GPT API."""
import openai
from utils import config_loader
from utils.logger import get_logger
from . import prompts

gpt_logger = get_logger(__name__)

if not config_loader.OPENAI_API_KEY:
    gpt_logger.error("OpenAI API Key not configured. Bot cannot use GPT functions.")
    client = None
else:
    client = openai.AsyncOpenAI(api_key=config_loader.OPENAI_API_KEY)

GPT_MODEL = config_loader.get_config("gpt_settings.model", "gpt-4.1-mini")
GPT_TEMPERATURE = config_loader.get_config("gpt_settings.temperature", 1.0)
GPT_MAX_TOKENS = config_loader.get_config("gpt_settings.max_tokens", 2048)
GPT_MAX_TOKENS_LANG_DETECT = config_loader.get_config("gpt_settings.max_tokens_lang_detect", 10)
GPT_MAX_TOKENS_TRANSLATE = config_loader.get_config("gpt_settings.max_tokens_translate", 300)

async def _call_gpt_api(system_prompt: str, user_content: str, max_tokens: int) -> str | None:
    """Internal helper function for GPT API calls."""
    if not client:
        gpt_logger.error("OpenAI Client not initialized. API call skipped.")
        return None
    try:
        response = await client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=GPT_TEMPERATURE,
            max_tokens=max_tokens,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            result = response.choices[0].message.content.strip()
            if result:
                return result
            else:
                gpt_logger.warning(f"GPT response content was empty after .strip() for system prompt: '{system_prompt[:50]}...'")
                return None
        else:
            gpt_logger.warning(f"No valid response from GPT for system prompt: '{system_prompt[:50]}...'")
            return None
    except openai.APIConnectionError as e:
        gpt_logger.error(f"OpenAI API connection error: {e}")
    except openai.RateLimitError as e:
        gpt_logger.error(f"OpenAI API rate limit exceeded: {e}")
    except openai.APIStatusError as e:
        gpt_logger.error(f"OpenAI API status error: {e.status_code} - {e.response}")
    except Exception as e:
        gpt_logger.error(f"Unexpected error during GPT request ('{system_prompt[:50]}...'): {e}")
    return None

async def analyze_text_with_gpt(text_to_analyze: str, system_prompt_template: str, leniency_level: int = 0) -> str | None:
    """
    Sends text to the OpenAI GPT API for analysis and returns the response.
    Now uses configuration values for model, temperature, and max tokens,
    and formats the system prompt with a leniency level.

    Args:
        text_to_analyze: The text to be analyzed by GPT.
        system_prompt_template: The system prompt template that controls GPT's behavior.
        leniency_level: An integer from 0 to 100 indicating moderation leniency.

    Returns:
        The text response from GPT or None in case of an error.
    """
    try:
        system_prompt = system_prompt_template.format(leniency_level=leniency_level)
    except KeyError as e:
        gpt_logger.error(f"Failed to format system prompt with leniency_level. Missing key: {e}. Prompt template: '{system_prompt_template[:100]}...'")
        system_prompt = system_prompt_template
        gpt_logger.warning("Proceeding with potentially unformatted system prompt due to KeyError.")

    gpt_logger.debug(f"analyze_text_with_gpt: Model={GPT_MODEL}, Leniency={leniency_level}, SysPrompt='{system_prompt[:70]}...', Text='{text_to_analyze[:50]}...'")
    return await _call_gpt_api(system_prompt, text_to_analyze, GPT_MAX_TOKENS)

async def detect_language_with_gpt(text_to_detect: str) -> str | None:
    """Detects the language of the text using GPT and returns the ISO 639-1 code."""
    gpt_logger.debug(f"detect_language_with_gpt: Text='{text_to_detect[:50]}...'")
    language_code = await _call_gpt_api(prompts.LANGUAGE_DETECTION_SYSTEM_PROMPT, text_to_detect, GPT_MAX_TOKENS_LANG_DETECT)
    if language_code and len(language_code) == 2 and language_code.isalpha():
        gpt_logger.info(f"Language detected by GPT as '{language_code}' for text: '{text_to_detect[:50]}...'")
        return language_code.lower()
    elif language_code == "unknown":
        gpt_logger.info(f"Language detected by GPT as 'unknown' for text: '{text_to_detect[:50]}...'")
        return "unknown"
    else:
        gpt_logger.warning(f"Invalid or no language code received from GPT ('{language_code}') for text: '{text_to_detect[:50]}...'")
        return None

async def translate_text_with_gpt(text_to_translate: str, target_language: str, base_system_prompt: str, **kwargs) -> str | None:
    """Translates text into the target language using GPT."""
    try:
        system_prompt = base_system_prompt.format(target_language=target_language, **kwargs)
    except KeyError as e:
        gpt_logger.error(f"Missing key '{e}' when formatting translation prompt. Kwargs: {kwargs}")
        return None
    
    gpt_logger.debug(f"translate_text_with_gpt: Text='{text_to_translate[:50]}...', TargetLang='{target_language}', SysPrompt='{system_prompt[:50]}...'")
    translated_text = await _call_gpt_api(system_prompt, text_to_translate, GPT_MAX_TOKENS_TRANSLATE)
    if translated_text:
        gpt_logger.info(f"Text successfully translated to '{target_language}': '{translated_text[:50]}...'")
    else:
        gpt_logger.warning(f"Error or empty response during translation to '{target_language}' for text: '{text_to_translate[:50]}...'")
    return translated_text

if __name__ == "__main__":
    import asyncio
    async def test_gpt():
        from dotenv import load_dotenv
        load_dotenv()
        global client 
        if not client and config_loader.OPENAI_API_KEY:
            client = openai.AsyncOpenAI(api_key=config_loader.OPENAI_API_KEY)
            gpt_logger.info("OpenAI Client re-initialized in test run.")

        if not client:
            gpt_logger.error("OpenAI Client could not be initialized. Test aborted.")
            return

        test_text = "Hello World! How are you today?"
        test_system_prompt = config_loader.get_config("gpt_settings.moderation_system_prompt", "You are a helpful assistant.")
        gpt_logger.info(f"Testing GPT integration with text: '{test_text}' and system prompt from Config/Default")
        result = await analyze_text_with_gpt(test_text, test_system_prompt)
        if result:
            gpt_logger.info(f"GPT test response: {result}")
        else:
            gpt_logger.warning("GPT test failed.")

    asyncio.run(test_gpt())