"""Minimal Imperal Cloud extension example."""
from imperal_sdk import Extension

ext = Extension("hello-world", version="1.0.0")


@ext.tool("greet", scopes=["public"], description="Greet a user by name")
async def greet(ctx, name: str = "World"):
    """Say hello to someone."""
    return {"message": f"Hello, {name}!"}


@ext.tool("save_note", scopes=["notes.write"], description="Save a note")
async def save_note(ctx, text: str):
    """Save a note using Tier 1 storage."""
    note = await ctx.store.create("notes", {"text": text})
    return {"id": note.id, "text": text}


@ext.tool("check_quota", description="Check if user has exceeded limits")
async def check_quota(ctx):
    """Check billing limits."""
    limits = await ctx.billing.check_limits()
    if limits.any_exceeded:
        return {"exceeded": True, "meters": limits.exceeded}
    return {"exceeded": False}


@ext.signal("on_user_login")
async def on_login(ctx, user):
    """Load recent notes when user logs in."""
    notes = await ctx.store.query("notes", where={"user_id": user.id}, limit=5)
    await ctx.skeleton.update("recent_notes", [n.data for n in notes])


@ext.schedule("daily_summary", cron="0 9 * * *")
async def daily_summary(ctx):
    """Send daily note count."""
    count = await ctx.store.count("notes")
    await ctx.notify(f"You have {count} notes.")
