
var contains = function(str, substr) {
    return str.indexOf(substr) != -1;
}

var slashes = new RegExp("/+", "g");

module.exports = function(unsafe_canonical_name) {
    unsafe_canonical_name = unsafe_canonical_name.trim()
    
    // Replace all double or more slashes by single slashes.
    unsafe_canonical_name = unsafe_canonical_name.replace(slashes, '/')
    
    if (contains(unsafe_canonical_name, "."))
        throw new Error("canonical_name may not contain dots")
    
    if (contains(unsafe_canonical_name, "\\"))
        throw new Error("canonical_name may not contain backward slashes")
    
    if (contains(unsafe_canonical_name, "\0"))
        throw new Error("canonical_name may not contain a zero byte value")
    
    // This '_hover' restriction could be resolved if we store and serve hover images differently.
    if (contains(unsafe_canonical_name, "_hover"))
        throw new Error("canonical_name may not contain the substring '_hover'")
    
    if (unsafe_canonical_name.indexOf("/") == 0)
        throw new Error("canonical_name may not start with a forward slash")
    
    if (unsafe_canonical_name === "")
        throw new Error("canonical_name may not be a empty string")
    
    var safe_canonical_name = unsafe_canonical_name
    return safe_canonical_name
}
