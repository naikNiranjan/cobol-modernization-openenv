from legacy_cobol_env.training.audit_java_sft_lengths import audit_rows, summarize_audit


class WordTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False):
        return text.split()

    def apply_chat_template(self, messages, tokenize: bool, add_generation_prompt: bool):
        rendered = " ".join(message["content"] for message in messages)
        if add_generation_prompt:
            rendered += " assistant"
        return rendered.split()


def test_java_sft_length_audit_flags_invoice_over_2048():
    rows = [
        {
            "task_id": "payroll_net_pay_001",
            "family_id": "decimal_copybook_payroll",
            "primary_training_target": False,
            "prompt": "short",
            "completion": "done",
            "messages": [
                {"role": "user", "content": "short"},
                {"role": "assistant", "content": "done"},
            ],
        },
        {
            "task_id": "invoice_occurs_001",
            "family_id": "invoice_occurs_totals",
            "primary_training_target": True,
            "prompt": "x " * 2040,
            "completion": "y " * 20,
            "messages": [
                {"role": "user", "content": "x " * 2040},
                {"role": "assistant", "content": "y " * 20},
            ],
        },
    ]

    results = audit_rows(rows, WordTokenizer(), max_seq_length=2048)
    summary = summarize_audit(results, max_seq_length=2048)

    invoice = [row for row in results if row["task_id"] == "invoice_occurs_001"][0]
    assert invoice["exceeds_max_seq_length"] is True
    assert summary["invoice_exceeds_max_seq_length"] is True
    assert summary["recommended_max_seq_length"] == 4096
