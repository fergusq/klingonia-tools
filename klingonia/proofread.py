from collections import defaultdict
import re

import yajwiz

def check_and_render(text: str):
    ans = "<table>"
    n_errors = 0
    for line in text.split("\n"):
        if not line.strip():
            continue
        
        ans += "<tr>"
        errors = yajwiz.get_errors(line)

        errors.sort(key=lambda e: e.location)
        error_dict = defaultdict(list)
        for error in errors:
            if re.search(r"\d", line[error.location:error.end_location]):
                continue
                
            error_dict[error.location].append(error)
            n_errors += 1
        
        if error_dict:
            ans += "<td>⚠️"
        
        else:
            ans += "<td>"
        
        close_dict = defaultdict(lambda: 0)
        ans += "<td okrand>"
        for i in range(len(line)):
            ans += "</span>" * close_dict[i]
            if i in error_dict:
                for error in sorted(error_dict[i], key=lambda e: e.end_location):
                    ans += f'<span class=error title="{error.message}">'
                    close_dict[error.end_location] += 1
                
            ans += line[i]

    ans += "</table>"
    return n_errors, ans