import json
import os


def pretty_print_json_file(input_path, output_path=None, indent=4):
    """
    Reads a JSON file, pretty-prints it to console or a new file.

    Args:
        input_path (str): Path to the original JSON file.
        output_path (str, optional): Where to save the pretty JSON. If None, prints to console.
        indent (int): Indentation level for formatting.
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        pretty_json = json.dumps(data, indent=indent, sort_keys=True, ensure_ascii=False)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(pretty_json)
            print(f"Saved prettified JSON to: {output_path}")
        else:
            print(pretty_json)

    except Exception as e:
        print(f"Error: {e}")


# Example usage
# Just update the path below:
input_file = 'testfile.json'
output_file = 'base_pretty.json'
pretty_print_json_file(input_file, output_file)
