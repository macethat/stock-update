<?php
require_once('wp-load.php');
$fields = WC()->checkout->get_checkout_fields('billing');
foreach ($fields as $key => $f) {
    if (strpos($key, 'doc_ident') !== false || strpos($key, 'ident') !== false) {
        echo "$key: " . json_encode($f) . "\n";
    }
}
echo "Total billing fields: " . count($fields) . "\n";
