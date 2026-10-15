import unittest

from copilot_gateway.slack_app import StreamRenderer


class _StubClient:
    def __init__(self) -> None:
        self.posts = []
        self.updates = []

    async def chat_postMessage(self, **kwargs):
        self.posts.append(kwargs)
        return {"ts": "123.456"}

    async def chat_update(self, **kwargs):
        self.updates.append(kwargs)


def _cancel_button(blocks):
    actions = [b for b in blocks if b["type"] == "actions"]
    return actions[0]["elements"][0]


class CancelButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_posts_cancel_button_with_conversation_key(self) -> None:
        client = _StubClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1:1700000000.000001")

        await renderer.start()

        button = _cancel_button(client.posts[0]["blocks"])
        self.assertEqual(button["action_id"], "cancel_turn")
        self.assertEqual(button["value"], "C1:1700000000.000001")
        self.assertEqual(button["style"], "danger")

    async def test_live_blocks_render_text_in_a_section(self) -> None:
        # With blocks present, Slack only displays block content — the message
        # text must live in a section block or the message renders button-only.
        client = _StubClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1")

        await renderer.start()

        sections = [b for b in client.posts[0]["blocks"] if b["type"] == "section"]
        self.assertEqual(sections[0]["text"]["text"], "⏳ Working…")

    async def test_live_updates_keep_the_button(self) -> None:
        client = _StubClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1")
        await renderer.start()

        await renderer.add_text("partial output")
        await renderer._maybe_update(force=True)

        blocks = client.updates[-1]["blocks"]
        self.assertEqual(_cancel_button(blocks)["action_id"], "cancel_turn")
        sections = [b for b in blocks if b["type"] == "section"]
        self.assertIn("partial output", sections[0]["text"]["text"])

    async def test_finalize_strips_the_button(self) -> None:
        client = _StubClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1")
        await renderer.start()
        await renderer.add_text("done")

        await renderer.finalize()

        self.assertEqual(client.updates[-1]["blocks"], [])

    async def test_finalize_on_cancel_keeps_partial_output(self) -> None:
        client = _StubClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1")
        await renderer.start()
        await renderer.add_text("partial answer")

        await renderer.finalize(cancelled=True)

        update = client.updates[-1]
        self.assertEqual(update["blocks"], [])
        self.assertIn("partial answer", update["text"])
        self.assertIn("Cancelled", update["text"])
        self.assertNotIn("no response", update["text"])

    async def test_finalize_on_cancel_without_any_output(self) -> None:
        client = _StubClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1")
        await renderer.start()

        await renderer.finalize(cancelled=True)

        update = client.updates[-1]
        self.assertIn("Cancelled", update["text"])
        self.assertNotIn("no response", update["text"])

    async def test_finalize_retries_as_plain_text_when_block_update_fails(self) -> None:
        class FlakyClient(_StubClient):
            fail_next_update = False

            async def chat_update(self, **kwargs):
                if self.fail_next_update:
                    self.fail_next_update = False
                    raise RuntimeError("rate limited")
                await super().chat_update(**kwargs)

        client = FlakyClient()
        renderer = StreamRenderer(client, "C1", None, False, conv_key="C1")
        await renderer.start()
        await renderer.add_text("kept despite the hiccup")
        client.fail_next_update = True

        await renderer.finalize()

        self.assertEqual(client.updates[-1]["text"], "kept despite the hiccup")
        self.assertNotIn("blocks", client.updates[-1])


if __name__ == "__main__":
    unittest.main()
