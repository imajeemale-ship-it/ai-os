"""Load manually inspected frame notes only for the exact source media."""
import hashlib
import json
from pathlib import Path


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(directory, source_path, technical):
    """Reject stale annotations and unsupported timestamps; never infer unseen footage."""
    note_file = Path(directory) / 'human_review.json'
    if not note_file.is_file():
        return None
    if source_path is None:
        raise ValueError('Human notes require a source video for hash verification')
    data = json.loads(note_file.read_text())
    digest = data.get('source_sha256', '')
    if not isinstance(digest, str) or len(digest) != 64 or digest != file_sha256(source_path):
        raise ValueError('Human frame notes do not match the source video SHA-256')
    frames = technical.get('frames', [])
    sampled = [frame.get('timestamp_seconds') for frame in frames]
    duration = technical.get('duration_seconds', 0)
    notes = data.get('observations', [])
    if not isinstance(notes, list) or len(notes) > 32:
        raise ValueError('Human frame observations must be a list of at most 32 entries')
    validated = []
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError('Invalid human frame observation')
        t = note.get('timestamp_seconds')
        observation = note.get('observation')
        question = note.get('editor_question')
        if (not isinstance(t, (int, float)) or isinstance(t, bool) or
            not 0 <= t <= duration or
            not any(isinstance(s, (int, float)) and abs(s - t) <= 0.2 for s in sampled) or
            not isinstance(observation, str) or not 0 < len(observation.strip()) <= 300 or
            not isinstance(question, str) or not 0 < len(question.strip()) <= 300):
            raise ValueError('Human frame note requires a sampled timestamp, observation, and review question')
        validated.append({'timestamp_seconds': t, 'observation': observation.strip(),
                          'editor_question': question.strip()})
    return {'observations': validated, 'source_sha256': digest,
            'evidence_source': 'human_inspected_sampled_frame'}
