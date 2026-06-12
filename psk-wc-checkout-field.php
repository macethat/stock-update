<?php
/**
 * Plugin Name: PSK WC Checkout Field
 * Description: Agrega campo Cedula/RUC obligatorio al checkout
 * Version: 1.0
 */

add_filter('woocommerce_billing_fields', 'psk_add_cedula_field');
function psk_add_cedula_field($fields) {
    $fields['billing_doc_identificacion'] = array(
        'label'       => 'Cedula/Pasaporte/RUC',
        'required'    => true,
        'class'       => array('form-row-wide'),
        'priority'    => 25,
    );
    return $fields;
}

add_action('woocommerce_checkout_update_order_meta', 'psk_save_cedula_field');
function psk_save_cedula_field($order_id) {
    if (!empty($_POST['billing_doc_identificacion'])) {
        update_post_meta($order_id, '_doc_identificacion', sanitize_text_field($_POST['billing_doc_identificacion']));
    }
}

add_action('woocommerce_admin_order_data_after_billing_address', 'psk_display_cedula_admin', 10, 1);
function psk_display_cedula_admin($order) {
    $cedula = $order->get_meta('_doc_identificacion');
    if ($cedula) {
        echo '<p><strong>Cedula / RUC:</strong> ' . esc_html($cedula) . '</p>';
    }
}
