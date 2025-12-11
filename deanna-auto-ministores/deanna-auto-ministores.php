<?php
/*
Plugin Name: Deanna Auto Ministores
Description: Extrae dos temas comerciales con GPT y genera enlaces de mini tiendas deanna2u.com para cada artículo al publicarlo.
Version: 0.1
Author: Deanna
*/

if (!defined('ABSPATH')) exit;

define('DEANNA_MINISTORES_META_KEY', '_deanna_ministores_json');

/**
 * Generate ministores on post publish.
 */
function deanna_generate_ministores_on_save($post_id, $post, $update) {

    if (wp_is_post_revision($post_id)) return;
    if ($post->post_status !== 'publish') return;

    $existing = get_post_meta($post_id, DEANNA_MINISTORES_META_KEY, true);
    if (!empty($existing)) return;

    $content = wp_strip_all_tags($post->post_content);
    $content = trim($content);
    if (mb_strlen($content) < 200) return;

    if (mb_strlen($content) > 15000) {
        $content = mb_substr($content, 0, 15000);
    }

    if (!defined('DEANNA_OPENAI_API_KEY') || !DEANNA_OPENAI_API_KEY) {
        error_log('Deanna ministores: missing DEANNA_OPENAI_API_KEY');
        return;
    }

    $api_key = DEANNA_OPENAI_API_KEY;

    // ---------- COPY OF YOUR PYTHON SYSTEM PROMPT ----------
    $system_prompt = "Eres un experto en marketing digital especializado en identificar oportunidades comerciales...\n\n" .
        "Tu objetivo es extraer dos temas comerciales del artículo que sean perfectos para generar anuncios...\n\n" .
        "FORMATO DE RESPUESTA:\n" .
        "Devuelve EXACTAMENTE dos búsquedas comerciales, una por línea, sin numeración ni viñetas. Máximo 5 palabras.\n\n" .
        "EJEMPLOS:\n" .
        "mejores restaurantes Madrid centro\n" .
        "hoteles económicos Barcelona playa\n" .
        "cursos online marketing digital\n" .
        "smartphones gama media 2024\n" .
        "gimnasios cerca de mí";

    // ---------- COPY OF YOUR PYTHON USER PROMPT ----------
    $user_prompt = "Analiza el siguiente artículo periodístico e identifica DOS temas comerciales perfectos...\n\n" .
        "INSTRUCCIONES:\n" .
        "- Lee el artículo\n" .
        "- Identifica dos oportunidades comerciales\n" .
        "- Usa máximo 5 palabras\n" .
        "- Devuelve exactamente dos líneas\n\n" .
        "ARTÍCULO:\n" . $content;

    $body = array(
        "model" => "gpt-4o-mini",
        "messages" => array(
            array("role" => "system", "content" => $system_prompt),
            array("role" => "user", "content" => $user_prompt),
        ),
        "temperature" => 0.4,
    );

    $response = wp_remote_post(
        "https://api.openai.com/v1/chat/completions",
        array(
            "headers" => array(
                "Content-Type" => "application/json",
                "Authorization" => "Bearer " . $api_key,
            ),
            "body" => wp_json_encode($body),
            "timeout" => 90,
        )
    );

    if (is_wp_error($response)) {
        error_log('OpenAI error: ' . $response->get_error_message());
        return;
    }

    $resp_body = wp_remote_retrieve_body($response);
    $data = json_decode($resp_body, true);

    if (!isset($data['choices'][0]['message']['content'])) return;

    $raw_output = trim($data['choices'][0]['message']['content']);
    $lines = preg_split('/\r\n|\r|\n/', $raw_output);

    $topics = [];
    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '') continue;
        $line = preg_replace('/^\d+\.\s*/', '', $line);
        $topics[] = $line;
    }

    if (empty($topics)) return;

    $topics = array_slice($topics, 0, 2);

    $entries = [];
    foreach ($topics as $topic) {
        $words = preg_split('/\s+/', $topic);
        if (count($words) > 5) {
            $words = array_slice($words, 0, 5);
            $topic = implode(' ', $words);
        }

        $encoded = rawurlencode($topic);
        $url = "https://www.deanna2u.com/?q=" . $encoded;

        $entries[] = [
            "topic" => sanitize_text_field($topic),
            "url"   => esc_url_raw($url)
        ];
    }

    update_post_meta($post_id, DEANNA_MINISTORES_META_KEY, wp_json_encode($entries));
}

add_action('save_post', 'deanna_generate_ministores_on_save', 10, 3);


/**
 * Shortcode to display the box.
 */
function deanna_ministores_box_shortcode() {
    if (!is_singular('post')) return '';

    $json = get_post_meta(get_the_ID(), DEANNA_MINISTORES_META_KEY, true);
    if (empty($json)) return '';

    $entries = json_decode($json, true);
    if (!is_array($entries)) return '';

    ob_start(); ?>
    <div class="deanna-ministores-box">
        <h3>Tiendas relacionadas</h3>
        <ul>
        <?php foreach ($entries as $entry): ?>
            <li>
                <a href="<?php echo esc_url($entry['url']); ?>" target="_blank">
                    <?php echo esc_html($entry['topic']); ?>
                </a>
            </li>
        <?php endforeach; ?>
        </ul>
    </div>
    <?php
    return ob_get_clean();
}
add_shortcode('deanna_ministores_box', 'deanna_ministores_box_shortcode');


/**
 * Basic CSS
 */
function deanna_ministores_styles() {
    $css = "
    .deanna-ministores-box {
        border: 1px solid #4b5563;
        padding: 16px;
        border-radius: 10px;
        background: #111827;
        color: #f9fafb;
    }
    .deanna-ministores-box h3 {
        margin: 0 0 10px 0;
        color: #f97316;
    }
    .deanna-ministores-box ul {
        list-style: none;
        padding: 0;
        margin: 0;
    }
    .deanna-ministores-box li {
        margin-bottom: 6px;
    }
    .deanna-ministores-box a {
        color: #93c5fd;
        text-decoration: none;
    }
    .deanna-ministores-box a:hover {
        text-decoration: underline;
    }
    ";
    wp_add_inline_style('wp-block-library', $css);
}
add_action('wp_enqueue_scripts', 'deanna_ministores_styles');
