// Hello World — A simple Cy script example
//
// This task takes an optional name from the input and returns a greeting.
// It demonstrates: variable access, string formatting, and result return.

alert_title = inp.get("title") ?? "World"
greeting = f"Hello, {alert_title}! This is your first Cy task."

log(f"Generated greeting for: {alert_title}")

result = {
    "greeting": greeting,
    "input_received": inp
}
