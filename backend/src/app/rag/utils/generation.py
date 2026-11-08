import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_NAME = "facebook/opt-1.3b"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME, torch_dtype=torch.float16, device_map="auto"
)

def generate_answer_chat(query, options, retrieved_chunks, model=model, tokenizer=tokenizer):
    paragraphs = [f"Paragraph {idx+1}: {chunk}" for idx, chunk in enumerate(retrieved_chunks)]
    context = "\n\n".join(paragraphs)

    system_message = (
        "System: You are a telecom regulations expert. Answer using the information provided in the context. Start directly by Giving the best choice from options"
    )
    context_message = f"Context:\n{context}"
    user_message = f"User: {query}\nOptions: " + " | ".join(options)
    assistant_cue = "Assistant: "

    prompt = "\n\n".join([system_message, context_message, user_message, assistant_cue])

    model_type = "seq2seq" if getattr(model.config, "is_encoder_decoder", False) else "causal"
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    outputs = model.generate(
        **inputs,
        max_new_tokens=128,
        num_return_sequences=1,
        no_repeat_ngram_size=2
    )

    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

    if model_type == "causal":
        answer_start = generated_text.find("Assistant:")
        if answer_start != -1:
            answer = generated_text[answer_start + len("Assistant:"):].strip()
        else:
            answer = generated_text[len(prompt):].strip()
        return answer
    else:
        return generated_text.strip()


def generate_answer(query, retrieved_chunks, model=model, tokenizer=tokenizer):
    paragraphs = [f"Paragraph {idx+1}: {chunk}" for idx, chunk in enumerate(retrieved_chunks)]
    context = "\n\n".join(paragraphs)

    prompt = (f"You are a telecom regulations expert. Using the following context, answer the question:\n\n"
              f"Context:\n{context}\n\n"
              f"Question: {query}\nAnswer:")

    model_type = "seq2seq" if getattr(model.config, "is_encoder_decoder", False) else "causal"
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = model.generate(
        **inputs,
        max_new_tokens=2048,
        num_return_sequences=1,
        no_repeat_ngram_size=2
    )

    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

    if model_type == "causal":
        return generated_text[len(prompt):].strip()
    else:
        return generated_text.strip()


def generate_norag(query, model, tokenizer):
    prompt = f"Answer the question:\n\nQuestion: {query}\nAnswer:"
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    outputs = model.generate(
        **inputs,
        max_new_tokens=128,
        num_return_sequences=1,
        no_repeat_ngram_size=2
    )

    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    model_type = "seq2seq" if getattr(model.config, "is_encoder_decoder", False) else "causal"

    if model_type == "causal":
        return generated_text[len(prompt):].strip()
    else:
        return generated_text.strip()


