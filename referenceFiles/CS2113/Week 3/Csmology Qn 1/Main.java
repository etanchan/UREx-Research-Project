import java.util.Scanner;
import java.util.Arrays;

public class Main {
    public static String[] findExpenses(String sentence) {
        int wordCount = 0;
        String[] words = sentence.split(" ");
        String[] result = new String[words.length];

        for (String word : words) {
            if (word.startsWith("$")) {
                result[wordCount] = word;
                wordCount++;
            }
        }
        return Arrays.copyOf(result, wordCount);
    }

    public static double findTotal(String[] expenses) {
        double total = 0;
        for (String expense : expenses) {
            expense = expense.replace("$", "");
            total += Double.parseDouble(expense);
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.print("Your expenses while overseas?");

        String sentence;
        Scanner in = new Scanner(System.in);
        sentence = in.nextLine();

        String[] expenses = findExpenses(sentence);
        double totalLocalExpense = findTotal(expenses) * 1.7;

        System.out.println("Expenses in overseas currency:" + Arrays.toString(expenses));
        System.out.println("Total in local currency: $" + String.format("%.2f", totalLocalExpense));
    }
}