def resolve_domain(candidate_domain: str, jd_domain_synonyms: list[str], threshold: int = 80) -> bool:
    """
    Checks if a candidate's job domain matches any of the JD's domain synonyms.
    Uses fuzzy matching to handle slight variations in terminology.
    """
    # If candidate domain is unknown, don't penalize yet - let phase 1 math handle it
    if not candidate_domain or candidate_domain.lower() == "unknown":
        return True
        
    if not jd_domain_synonyms:
        return False
        
    try:
        from rapidfuzz import fuzz
        use_fuzz = True
    except ImportError:
        use_fuzz = False

    candidate_lower = candidate_domain.lower().strip()
    
    for synonym in jd_domain_synonyms:
        synonym_lower = synonym.lower().strip()
        
        # Exact/Sub-string match
        if candidate_lower in synonym_lower or synonym_lower in candidate_lower:
            return True
            
        # Fuzzy match fallback
        if use_fuzz:
            score = fuzz.partial_ratio(candidate_lower, synonym_lower)
            if score >= threshold:
                return True
                
    return False
