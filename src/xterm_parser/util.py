def convert_literal(input: str) -> str:
    result = input
    result.replace("CSI", "\x1b[")
    result.replace("OSC", "\x1b]")
    result.replace("SP", " ")
    result.replace("ST", "\x1b\\")
    result.replace(" ", "")

    return result
