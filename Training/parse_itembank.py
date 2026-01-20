#!/usr/bin/env python3
"""
Parse the itembank directory and generate a JSONL file for fine-tuning.

This script:
- Only processes English questions (folders ending with -en)
- Only includes questions with no external dependencies (single RMD file only)
- Extracts question and solution content from RMD files
- Generates prompts like "Write a statistics question on the topic of <topic>."
"""

import os
import json
import re
from pathlib import Path


def get_domain_folders(itembank_path: str) -> list[str]:
    """Get list of domain folders (excluding hidden folders and non-directories)."""
    domains = []
    for item in os.listdir(itembank_path):
        item_path = os.path.join(itembank_path, item)
        if os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('_'):
            # Skip non-domain folders
            if item not in ['packaging', 'scripts']:
                domains.append(item)
    return sorted(domains)


def is_english_question(folder_name: str) -> bool:
    """Check if the folder is for an English question (ends with -en)."""
    return folder_name.endswith('-en')


def has_no_external_dependencies(folder_path: str) -> bool:
    """Check if the folder contains only a single RMD file (no external dependencies)."""
    files = os.listdir(folder_path)
    if len(files) != 1:
        return False
    # Check that the single file is an RMD file
    return files[0].lower().endswith('.rmd')


def parse_rmd_file(rmd_path: str) -> dict | None:
    """
    Parse an RMD file and extract the question and solution.
    
    Returns a dict with 'question' and 'solution' keys, or None if parsing fails.
    """
    try:
        with open(rmd_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {rmd_path}: {e}")
        return None
    
    # Split content into sections
    # Sections are delimited by lines of ======== 
    sections = {}
    current_section = None
    current_content = []
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if next line is a section delimiter (========)
        if i + 1 < len(lines) and re.match(r'^=+\s*$', lines[i + 1]):
            # Save previous section
            if current_section:
                sections[current_section] = '\n'.join(current_content).strip()
            # Start new section
            current_section = line.strip().lower()
            current_content = []
            i += 2  # Skip the delimiter line
            continue
        else:
            if current_section:
                current_content.append(line)
        i += 1
    
    # Save last section
    if current_section:
        sections[current_section] = '\n'.join(current_content).strip()
    
    # Extract question and solution
    question = sections.get('question', '')
    solution = sections.get('solution', '')
    
    if not question or not solution:
        return None
    
    return {
        'question': question,
        'solution': solution
    }


def format_topic_name(domain_folder: str) -> str:
    """Convert domain folder name to a readable topic name."""
    # Replace hyphens and underscores with spaces
    topic = domain_folder.replace('-', ' ').replace('_', ' ')
    # Convert to lowercase for consistency
    topic = topic.lower()
    return topic


def create_training_example(topic: str, rmd_content: dict) -> dict:
    """
    Create a training example in the format for fine-tuning.
    
    Returns a dict with 'prompt' and 'completion' keys.
    """
    prompt = f"Write a statistics question on the topic of {topic}."
    
    # Combine question and solution for the completion
    completion = f"""Question
========
{rmd_content['question']}

Solution
========
{rmd_content['solution']}"""
    
    return {
        'prompt': prompt,
        'completion': completion
    }


def process_itembank(itembank_path: str, output_path: str) -> dict:
    """
    Process the entire itembank and generate a JSONL file.
    
    Returns statistics about the processing.
    """
    stats = {
        'total_folders_scanned': 0,
        'english_folders': 0,
        'folders_with_dependencies': 0,
        'successfully_parsed': 0,
        'parse_errors': 0,
        'by_domain': {}
    }
    
    training_examples = []
    
    # Get all domain folders
    domains = get_domain_folders(itembank_path)
    print(f"Found {len(domains)} domain folders: {domains}")
    
    for domain in domains:
        domain_path = os.path.join(itembank_path, domain)
        topic = format_topic_name(domain)
        stats['by_domain'][domain] = {'total': 0, 'included': 0}
        
        # Iterate through question folders in this domain
        for question_folder in os.listdir(domain_path):
            question_path = os.path.join(domain_path, question_folder)
            
            # Skip if not a directory
            if not os.path.isdir(question_path):
                continue
            
            stats['total_folders_scanned'] += 1
            stats['by_domain'][domain]['total'] += 1
            
            # Check if English
            if not is_english_question(question_folder):
                continue
            
            stats['english_folders'] += 1
            
            # Check for external dependencies
            if not has_no_external_dependencies(question_path):
                stats['folders_with_dependencies'] += 1
                continue
            
            # Find and parse the RMD file
            rmd_files = [f for f in os.listdir(question_path) if f.lower().endswith('.rmd')]
            if not rmd_files:
                continue
            
            rmd_path = os.path.join(question_path, rmd_files[0])
            rmd_content = parse_rmd_file(rmd_path)
            
            if rmd_content is None:
                stats['parse_errors'] += 1
                continue
            
            # Create training example
            example = create_training_example(topic, rmd_content)
            training_examples.append(example)
            stats['successfully_parsed'] += 1
            stats['by_domain'][domain]['included'] += 1
    
    # Write JSONL file
    with open(output_path, 'w', encoding='utf-8') as f:
        for example in training_examples:
            f.write(json.dumps(example, ensure_ascii=False) + '\n')
    
    print(f"\nWrote {len(training_examples)} training examples to {output_path}")
    
    return stats


def main():
    # Determine paths
    script_dir = Path(__file__).parent
    itembank_path = script_dir / 'itembank'
    output_path = script_dir / 'finetune_data.jsonl'
    
    if not itembank_path.exists():
        print(f"Error: itembank directory not found at {itembank_path}")
        return
    
    print(f"Processing itembank at: {itembank_path}")
    print(f"Output will be written to: {output_path}")
    print("-" * 60)
    
    stats = process_itembank(str(itembank_path), str(output_path))
    
    # Print statistics
    print("\n" + "=" * 60)
    print("PROCESSING STATISTICS")
    print("=" * 60)
    print(f"Total question folders scanned: {stats['total_folders_scanned']}")
    print(f"English folders (-en): {stats['english_folders']}")
    print(f"Excluded (external dependencies): {stats['folders_with_dependencies']}")
    print(f"Parse errors: {stats['parse_errors']}")
    print(f"Successfully included: {stats['successfully_parsed']}")
    
    print("\n" + "-" * 60)
    print("BY DOMAIN:")
    print("-" * 60)
    for domain, domain_stats in sorted(stats['by_domain'].items()):
        print(f"  {domain}: {domain_stats['included']}/{domain_stats['total']} included")


if __name__ == '__main__':
    main()
